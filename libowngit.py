# import libraries
import argparse # for parsing command line arguments
import collections # for OrderedDict (few more container types than the base lib)
import configparser # for parsing configuration files (git uses a configuration file that is basically Microsoft's .ini format)
from datetime import datetime # for datetime objects
import grp, pwd # for group and user information (to display nicely)
from fnmatch  import fnmatch # for globbing (to support .gitignore)
import hashlib # for hashing (git uses SHA-1 function quite extensively)
from math import ceil # for rounding up
import os # for filesystem operations
import re # for regular expressions
import sys # for system operations
import zlib # for compression (git uses zlib to compress objects)

# add arguments
argparser = argparse.ArgumentParser(description='The clueless code collector')
# need to handle subcommands (init, add, etc.)
argsubparsers = argparser.add_subparsers(title='Commands', dest='command')
argsubparsers.required = True

# dest='command' argument that the name of the chosen subparser will be returned as a string in a variable called command
def main(argv=sys.argv[1:]):
    args = argparser.parse_args(argv)
    if args.command == "add":
        cmd_add(args)
    elif args.command == "cat-file":
        cmd_cat_file(args)
    elif args.command == "check-ignore":
        cmd_check_ignore(args)
    elif args.command == "checkout":
        cmd_checkout(args)
    elif args.command == "commit":
        cmd_commit(args)
    elif args.command == "hash-object":
        cmd_hash_object(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "ls-files":
        cmd_ls_files(args)
    elif args.command == "ls-tree":
        cmd_ls_tree(args)
    elif args.command == "rev-parse":
        cmd_rev_parse(args)
    elif args.command == "rm":
        cmd_rm(args)
    elif args.command == "show-ref":
        cmd_show_ref(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "tag":
        cmd_tag(args)
    else:
        print("Bad command.")

# git repository
class GitRepository:
    """A git repository"""

    worktree = None # the working directory
    gitdir = None # the git directory
    conf = None # the configuration

    def __init__(self, path, force=False): # constructor takes an optional force argument which disables all checks
        self.worktree = path # the working directory
        self.gitdir = os.path.join(path, '.git') # the git directory

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f'Not a git repository {path}') # if the git directory does not exist, raise an exception
        
        # read the configuration file in .git/config
        self.conf = configparser.ConfigParser() # create a configuration parser object
        cf = repo_file(self, 'config') # get the configuration file

        if cf and os.path.exists(cf):
            self.conf.read([cf]) # read the configuration file
        elif not force:
            raise Exception('Configuration file missing') # if the configuration file does not exist, raise an exception
        
        # check the version of the configuration file
        if not force:
            vers = int(self.conf.get('core', 'repositoryformatversion')) # get the version of the configuration file
            if vers != 0:
                raise Exception(f'Unsupported repositoryformatversion {vers}') # if the version is not 0, raise an exception

############################################################################################
#------------------------------------ REPOSITORY FUNCTIONS --------------------------------#
############################################################################################

def repo_path(repo, *path):
    """Compute path under repo's gitdir."""
    return os.path.join(repo.gitdir, *path) # join the path with the git directory

def repo_file(repo, *path, mkdir=False):
    """Same as repo_path, but create dirname(*path) if absent. For example, repo_file(r, 'refs', 'remotes', 'origin', 'HEAD') will create .git/refs/remotes/origin."""
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path) # return the path

def repo_dir(repo, *path, mkdir=False):
    """Same as repo_path, but mkdir *path if absent if mkdir is True."""
    path = repo_path(repo, *path) # get the path
    if os.path.exists(path): # if the path exists
        if os.path.isdir(path): # if the path is a directory
            return path # return the path
        else:
            raise Exception(f'Not a directory {path}') # otherwise, raise an exception
    if mkdir: # if the path does not exist and mkdir is True
        os.makedirs(path) # make the directory
        return path # return the path
    else:
        return None # otherwise, return None

def repo_create(path):
    """Create a new repository at path."""
    repo = GitRepository(path, True) # create a new repository
    # make sure the directory exists
    # first we make sure the path either doesn't exist or is an empty directory
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree): # if the path is not a directory
            raise Exception ("%s is not a directory!" % path) # raise an exception
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir): # if the git directory exists and is not empty
            raise Exception("%s is not empty!" % path) # raise an exception
    else: # if the path does not exist
        os.makedirs(repo.worktree) # make the directory

    assert repo_dir(repo, "branches", mkdir=True) # make the branches directory (.git/branches)
    assert repo_dir(repo, "objects", mkdir=True)  # make the objects directory (.git/objects)
    assert repo_dir(repo, "refs", "tags", mkdir=True) # make the tags directory (.git/refs/tags)
    assert repo_dir(repo, "refs", "heads", mkdir=True) # make the heads directory (.git/refs/heads)

    # .git/description
    with open(repo_file(repo, "description"), "w") as f: # open the description file
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n") # write to the description file

    # .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f: # open the HEAD file
        f.write("ref: refs/heads/master\n") # write to the HEAD file

    with open(repo_file(repo, "config"), "w") as f: # open the config file
        config = repo_default_config() # get the default configuration
        config.write(f) # write the default configuration to the config file

    return repo

def repo_default_config(): # create a default configuration
    ret = configparser.ConfigParser() # create a configuration parser object

    ret.add_section("core") # add a core section
    ret.set("core", "repositoryformatversion", "0") # set the repository format version
    ret.set("core", "filemode", "false") # set the file mode
    ret.set("core", "bare", "false") # set the bare flag

    return ret

# init command
argsp = argsubparsers.add_parser('init', help='Initialize a new, empty repository.')
argsp.add_argument('path',
    metavar='directory',
    nargs='?',
    default='.',
    help='Where to create the repository.')

def cmd_init(args):
    repo_create(args.path)

# repository find function (to find the root of the current repository)
def repo_find(path=".", required=True):
    path = os.path.realpath(path) # get the real path

    if os.path.isdir(os.path.join(path, ".git")): # if the .git directory exists
        return GitRepository(path) # return the repository

    # If we haven't returned, recurse in parent, if w
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        # Bottom case
        # os.path.join("/", "..") == "/":
        # If parent==path, then path is root.
        if required: # if required is True
            raise Exception("No git directory.") # raise an exception
        else: # otherwise
            return None # return None

    # Recursive case
    return repo_find(parent, required) # find the repository in the parent directory

############################################################################################
#---------------------------------- HASH OBJECT & CAT FILE --------------------------------#
############################################################################################

