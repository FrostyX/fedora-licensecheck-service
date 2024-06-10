import os
import logging
import shutil
import tempfile
import subprocess
import tarfile
import pyrpkg
import json
from specfile import Specfile


def get_log():
    log = logging.getLogger("fedora-licensecheck-service")

    log.setLevel(logging.INFO)

    # Drop the default handler, we will create it ourselves
    log.handlers = []

    # Print also to stderr
    stream = logging.StreamHandler()
    stream.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(stream)

    # Add file logging
    # path = config["log"]  # FIXME
    path = None
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_log = logging.FileHandler(path)
        file_log_format = "[%(asctime)s][%(levelname)6s]: %(message)s"
        file_log.setFormatter(logging.Formatter(file_log_format))
        log.addHandler(file_log)

    return log


log = get_log()


def consume(message):
    try:
        handle_message(message)
    except Exception:
        log.exception("Exception from message: %s", message.id)


def handle_message(message):
    if message.topic != "org.fedoraproject.prod.buildsys.build.state.change":
        return

    # TODO Too many messages come through. We need to limit this to only started
    # or finished builds. Possibly SRPM builds.

    log.info("Recognized Koji message: %s", message.id)

    url = message.body["request"][0]
    cloneurl, commit = url.split("git+")[1].split("#")
    reponame = cloneurl.replace("https://src.fedoraproject.org/", "")
    reponame = reponame.rsplit(".git", 1)[0]
    repodir = tempfile.mkdtemp()

    commands = pyrpkg.Commands(
        path=repodir,
        lookaside="https://src.fedoraproject.org/repo/pkgs",
        lookasidehash="sha512",
        lookaside_cgi="https://src.fedoraproject.org/repo/pkgs/upload.cgi",
        gitbaseurl="ssh://%(user)s@pkgs.fedoraproject.org/%(repo)s",
        anongiturl="https://src.fedoraproject.org/%(repo)s.git",
        branchre="",
        kojiprofile="koji",
        build_client="koji",
        allow_pre_generated_srpm=True)

    commands.clone(reponame, target=repodir, anon=True, skip_hooks=True)
    commands.repo.git.checkout(commit)
    commands.sources(repodir)

    spec = os.path.join(repodir, message.body["name"] + ".spec")
    specfile = Specfile(spec)
    storage = "/tmp/fedora-licensecheck-service/"

    dirname = "-".join([
        message.id,
        str(message.body["build_id"]),
        message.body["task"]["arch"],
    ])
    resultdir = os.path.join(storage, dirname)
    os.makedirs(resultdir)

    path = os.path.join(resultdir, "message.json")
    with open(path, "w+") as fp:
        json.dump({
            "id": message.id,
            "topic": message.topic,
            "body": message.body,
        }, fp)

    log.info("Created: %s", path)

    path = os.path.join(resultdir, "spec-license.txt")
    with open(path, "w+") as fp:
        fp.write(specfile.license + "\n")
    log.info("Created: %s", path)

    filenames = [x for x in os.listdir(repodir) if x.endswith(".tar.gz")]
    for i, filename in enumerate(filenames):
        path = os.path.join(repodir, filename)
        with tarfile.open(path) as tar:
            tar.extractall(path=repodir)
        extracted = path.rsplit(".tar.gz")[0]

        # Run licensecheck, scancode-toolkit, submit the sources to a dedicated
        # service, or do whatever you want to scan the sources
        cmd = ["licensecheck", "-r", extracted]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()

        path = os.path.join(resultdir, "licensecheck-{0}.txt".format(i))
        with open(path, "w+") as fp:
            fp.write(stdout.decode("utf-8"))
        log.info("Created: %s", path)

    shutil.rmtree(repodir)
    log.info("Finished processing %s", message.id)


if __name__ == "__main__":
    consume(consume)
