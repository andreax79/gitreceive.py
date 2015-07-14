gitreceive.py
=============

This is a Python porting of the bash gitreceive (https://github.com/progrium/gitreceive).

Why? Because I hate shell scripts.

Creates an ssh+git user that accepts on the fly repository pushes and triggers a hook script. 

Push code anywhere. Extend your Git workflow.

gitreceive.py dynamically creates bare repositories with a special `pre-receive` hook that triggers your own general gitreceive hook giving you easy access to the code that was pushed while still being able to send output back to the git user.

## Requirements

You need a Linux server with `git`, `sshd` and `python >= 2.5` installed.

## Installing

On your server, download https://raw.github.com/andreax79/gitreceive.py/master/gitreceive.py to a location on your $PATH and make it executable.

## Using gitreceive.py

#### Set up a git user on the server

This automatically makes a user and home directory if it doesn't exist. 

    $ sudo gitreceive.py init
    Created receiver script in /home/git for user 'git'.

You use a different user by setting `GITUSER=somethingelse` in the
environment before using `gitreceive.py`.

#### Modify the receiver script

As an example receiver script, it will POST all the data to a RequestBin:

    $ cat /home/git/receiver
    #!/bin/bash
    URL=http://requestb.in/rlh4znrl
    echo "----> Posting to $URL ..."
    curl \
      -X 'POST' \
      -F "repository=$1" \
      -F "revision=$2" \
      -F "username=$3" \
      -F "fingerprint=$4" \
      -F contents=@- \
      --silent $URL
    
The username is just a name associated with a public key. The
fingerprint of the key is sent so you can authenticate against the
public key that you may have for that user. 

Commands do not have access to environment variables from the `/etc/profile` directory, so if you need access to them, you will need to maually `source /etc/profile` - or any other configuration file - within your receiver script.

The repo contents are streamed into `STDIN` as an uncompressed archive (tar file). You can extract them into a directory on the server with a line like this in your receiver script:

    mkdir -p /some/path && cat | tar -x -C /some/path


#### Create a user by uploading a public key from your laptop

We just pipe our local SSH key into the `gitreceive.py upload-key` command via SSH:

    $ cat ~/.ssh/id_rsa.pub | ssh you@yourserver.com "sudo gitreceive.py upload-key [username]"

The `username` optional argument is just an arbitrary name associated with the key, mostly
for use in your system for auth, etc. If not provided, the username is extracted from the key.

`gitreceive.py upload-key` will authorize this key for use on the `$GITUSER`
account on the server, and use the SSH "forced commands" syntax in the remote
`.ssh/authorized_keys` file,  causing the internal `gitreceive.py run` command to
be called when this key is used with the remote git account. This allows us to
intercept the `git` requests and set up a `pre-receive` hook to run on the
repo, which triggers the custom receiver script.

#### Add a remote to a local repository

    $ git remote add demo git@yourserver.com:example

The repository `example` will be created on the fly when you push.

#### Push!!

    $ git push demo master
    Counting objects: 5, done.
    Delta compression using up to 4 threads.
    Compressing objects: 100% (3/3), done.
    Writing objects: 100% (3/3), 332 bytes, done.
    Total 3 (delta 1), reused 0 (delta 0)
    ----> Receiving progrium/gitreceive.git ... 
    ----> Posting to http://requestb.in/rlh4znrl ...
    ok
    To git@gittest:progrium/gitreceive.git
       59aa541..6eafb55  master -> master

The receiver script did not attempt to silence the output of curl, so
the respones of "ok" from RequestBin is shown. Use this to your
advantage! You can even use chunked-transfer encoding to stream back
progress in realtime if you wanted to keep using HTTP. Alternatively, you can have the
receiver script run any other script on the server.

## Big Thanks

gitreceive

## License

MIT
