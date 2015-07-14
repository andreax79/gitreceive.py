#!/usr/bin/env python

import os
import sys
import pwd
import glob
import subprocess
import base64
import hashlib

RUN_ONLY_ON_MASTER_BRANCH = False

try:
    from subprocess import DEVNULL # py3k
except ImportError:
    DEVNULL = open(os.devnull, 'wb')

def chown(glob_expression, username):
    """
        Change owner
    """
    uid = pwd.getpwnam(username).pw_uid
    for file in glob.glob(glob_expression):
        os.chown(file, uid, -1)

def touch(filename):
    """
        Sets the modification and access times of file to the current time of day or
        create a file with default permissions if it doesn't exist.
    """
    try:
        os.utime(filename, None)
    except:
        open(filename, 'a').close()

def setup_git_user(home_dir, git_user):
    """
        Create a Git user on the system, with home directory and an
        .authorized_keys file that contains the public keys or all
        users that are allowed to push their repos here.
    """
    subprocess.call(['useradd', '-d', home_dir, git_user], stdout=DEVNULL, stderr=subprocess.STDOUT)
    try:
        os.makedirs(os.path.join(home_dir, '.ssh'))
    except:
        pass
    touch(os.path.join(home_dir, '.ssh', 'authorized_keys'))
    chown(home_dir, git_user)

def setup_receiver_script(home_dir, git_user):
    """
        Creates a sample receiver script.
        This is the script that is triggered after a successful push.
    """
    local_receiver_path = os.path.join(home_dir, 'receiver')
    if not os.path.exists(local_receiver_path):
        f = open(local_receiver_path, 'w')
        f.write("""#!/bin/bash
#URL=http://requestb.in/rlh4znrl
#echo "----> Posting to \$URL ..."
#curl \\
#  -X 'POST' \\
#  -F "repository=\$1" \\
#  -F "revision=\$2" \\
#  -F "username=\$3" \\
#  -F "fingerprint=\$4" \\
#  -F contents=@- \\
#  --silent \$URL
""")
        f.close()
    os.chmod(local_receiver_path, 493) # 755
    chown(local_receiver_path, git_user)

def generate_fingerprint(key):
    """
        Generate a shorter, but still unique, version of the public key
        associated with the user doing `git push'
    """
    m = hashlib.md5()
    m.update(base64.b64decode(key))
    return ':'.join(['%02x' % ord(x) for x in m.digest()])

def install_authorized_key(line, name, home_dir, git_user):
    """
        Given a public key, add it to the .authorized_keys file with a
        'forced command'. The 'forced command' is a syntax specific to
        SSH's `.authorized_keys' file that allows you to specify a command
        that is run as soon as a user logs in.

        Note that even though `git push' does not explicitly mention SSH,
        it is nevertheless using the SSH protocol under the hood.

        See: http://man.finalrewind.org/1/ssh-forcecommand/
    """
    this_script = os.path.abspath(__file__)
    parts = line.split()
    if len(parts) < 2:
        print('Invalid key %s' % key)
        return False
    # Calculate the fingerprint
    fingerprint = generate_fingerprint(parts[1])
    # Extract the name from the key
    if not name:
        name = len(parts) > 2 and parts[2] or fingerprint
    forced_command = 'GITUSER=%s %s run %s %s' % (git_user, this_script, name, fingerprint)
    key_options = 'command="%s",no-agent-forwarding,no-pty,no-user-rc,no-X11-forwarding,no-port-forwarding %s\n' % (forced_command, line.strip())
    f = open(os.path.join(home_dir, '.ssh', 'authorized_keys'), 'a')
    f.write(key_options)
    f.close()
    print(fingerprint)

def parse_repo_from_ssh_command(cmd):
    """
        Get the repo from the incoming SSH command.
        This is needed as the original intended response to `git push' is
        overridden by the use of a 'forced command' (see install_authorized_key()).
        The forced command needs to know what repo to act on.
    """
    try:
        path = cmd.split()[1].strip('\'').strip('"').lstrip('/')
        if '..' in path:
            return None
        return path
    except:
        return None

def ensure_bare_repo(repo_path):
    """
    Create a git-enabled folder ready to receive git activity, like `git push'
    """
    if not os.path.exists(repo_path):
        subprocess.call(['git', 'init', '--bare', repo_path], stdout=DEVNULL, stderr=subprocess.STDOUT)

def ensure_prereceive_hook(repo_path, home_dir):
    """
    Create a Git pre-receive hook in a git repo that runs `gitreceive hook'
    when the repo receives a new git push
    """
    this_script = os.path.abspath(__file__)
    hook_path = os.path.join(repo_path, 'hooks', 'pre-receive')
    f = open(hook_path, 'w')
    f.write("""#!/bin/bash
cat | %s hook
""" % this_script)
    f.close()
    os.chmod(hook_path, 493) # 755

# When a repo receives a push, its pre-receive hook is triggered. This in turn executes `gitreceive hook', which is a
# wrapper around this function. The repo is updated and its working tree tarred so that it can be piped to
# `$home_dir/receiver'. The receiver script is setup by `setup_receiver_script()'.
def trigger_receiver(repo, user, fingerprint, home_dir):
    # oldrev, newrev, refname are a feature of the way in
    # which Git executes the pre-receive hook.
    # See https://www.kernel.org/pub/software/scm/git/docs/githooks.html
    for line in sys.stdin:
        tmp = line.split()
        if len(tmp) > 2: 
            oldrev = tmp[0]
            newrev = tmp[1]
            refname = tmp[2]
            # Only run this script for the master branch.
            if refname == 'refs/heads/master' or not RUN_ONLY_ON_MASTER_BRANCH:
                p1 = subprocess.Popen([ 'git', 'archive', newrev], stdout=subprocess.PIPE)
                p2 = subprocess.Popen([ os.path.join(home_dir, 'receiver'), repo, newrev, user, fingerprint ], stdin=p1.stdout, stdout=subprocess.PIPE)
                p1.stdout.close()
                output = p2.communicate()[0] 
                for l in output.split('\n'):
                    print(l.split('remote: ', 1)[-1])

# gitreceive.py init
def init(argv, git_user, home_dir):
    setup_git_user(home_dir, git_user)
    setup_receiver_script(home_dir, git_user)
    print("Created receiver script in %s for user '%s'." % (home_dir, git_user))

# sudo gitreceive.py upload-key [username]
def upload_key(argv, git_user, home_dir):
    name = len(argv) > 2 and argv[2] or None
    for line in sys.stdin:
        if line and not line.startswith('#'):
            install_authorized_key(line, name, home_dir, git_user)

# Called by the 'forced command' when the git user first authenticates against the server
def run(argv, git_user, home_dir):
    if len(argv) < 4:
        print("ERROR: Missing arguments")
        return False
    user = argv[2]
    fingerprint = argv[3]
    repo = parse_repo_from_ssh_command(os.environ['SSH_ORIGINAL_COMMAND'])
    if not repo: 
        print("ERROR: Arbitrary ssh prohibited!")
        return False
    repo_path = os.path.join(home_dir, repo)
    ensure_bare_repo(repo_path)
    ensure_prereceive_hook(repo_path, home_dir)

    os.environ['RECEIVE_USER'] = user
    os.environ['RECEIVE_FINGERPRINT'] = fingerprint
    os.environ['RECEIVE_REPO'] = repo 
    os.chdir(home_dir)

    # $SSH_ORIGINAL_COMMAND is set by `sshd'. It stores the originally
    # intended command to be run by `git push'. In our case it is
    # overridden by the 'forced command', so we need to reinstate it
    # now that the 'forced command' has run.
    cmd = os.environ['SSH_ORIGINAL_COMMAND'].split()[0]

    # subprocess.call([ 'git-shell', '-c', cmd, repo ], stdout=DEVNULL, stderr=subprocess.STDOUT)
    subprocess.call([ 'git-shell', '-c', "%s '%s'" % (cmd, repo) ])

# Called by the pre-receive hook
def hook(argv, git_user, home_dir):
    trigger_receiver(os.environ['RECEIVE_REPO'], os.environ['RECEIVE_USER'], os.environ['RECEIVE_FINGERPRINT'], home_dir)

COMMANDS = {
    # Public commands
    'init': init, 
    'upload-key': upload_key,
    # Internal commands
    'run': run,
    'hook': hook,
}

def main(argv):
    git_user = os.environ.get('GITUSER', 'git')
    try:
        home_dir = pwd.getpwnam(git_user)[5]
    except:
        home_dir = os.path.join('/home', git_user)

    cmd = len(argv) > 1 and COMMANDS.get(argv[1]) or None
    if cmd is not None:
        cmd(argv, git_user, home_dir)
    else:
        print("Usage: %s <command> [options]" % argv[0])
        sys.exit(2)

if __name__ == "__main__":
    main(sys.argv)

