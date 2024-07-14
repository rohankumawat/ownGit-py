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

class GitObject(object): # base class for all git objects (a generic object object)
    def __init__(self, data=None): # constructor
        if data != None:
            self.deserialize(data)
        else:
            self.init()
    
    def serialize(self, repo): # serialize the object
        """This function will be implemented by subclasses.
        
        It must read the object's contents from self.data, a byte string, and do whatever it takes to convert it into a meaningful representation.
        What exactly that means depends on each subclass (the type of object, so this is an abstract method.)"""
        raise Exception("Unimplemented!")
    
    def deserialize(self, data): # deserialize the object
        raise Exception("Unimplemented!") # this is an abstract method
    
    def init(self): # initialize the object
        pass # Just do nothing. Subclasses can implement it if they want. This is reasonable default!

# to read an object, we need to know its SHA-1 hash.
def object_read(repo, sha): # read an object from the repository
    """Read object sha from Git repository repo.  Return a
    GitObject whose exact type depends on the object."""

    path = repo_file(repo, "objects", sha[0:2], sha[2:]) # get the path of the object

    if not os.path.isfile(path): # if the object does not exist
        return None # return None

    with open (path, "rb") as f: # open the object file
        raw = zlib.decompress(f.read()) # read the object file and decompress it

        # Read object type
        x = raw.find(b' ') # find the first space
        fmt = raw[0:x] # get the object type

        # Read and validate object size
        y = raw.find(b'\x00', x) # find the first null byte
        size = int(raw[x:y].decode("ascii")) # get the object size
        if size != len(raw)-y-1: # if the size is not equal to the length of the object
            raise Exception("Malformed object {0}: bad length".format(sha)) # raise an exception

        # Pick constructor
        if fmt == b'commit':
            c = GitCommit # if the object is a commit
        elif fmt == b'tree':
            c = GitTree # if the object is a tree
        elif fmt == b'tag':
            c = GitTag # if the object is a tag
        elif fmt == b'blob':
            c = GitBlob # if the object is a blob
        else:
            raise Exception("Unknown type {0} for object {1}".format(fmt.decode("ascii"), sha)) # raise an exception    

        # Call constructor and return object
        return c(raw[y+1:])
    
# writing objects
# writing an object is reading it in reverse
# 1. compute the object's hash
# 2. insert the header
# 3. zlib-compress everything
# 4. write the result in the correct location
def object_write(obj, repo=None):
    # Serialize object data
    data = obj.serialize()
    # Add header
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    # Compute hash
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # Compute path
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, 'wb') as f:
                # Compress and write
                f.write(zlib.compress(result))
    return sha

# working with blobs (git has 4 object types: commit, tree, tag, and blob)
# blobs are the simplest objects (because they have no actual format)
# they are user data (all the files are stored as blobs)

class GitBlob(GitObject):
    fmt=b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

# cat-file command
argsp = argsubparsers.add_parser("cat-file",
                                 help="Provide content of repository objects")

argsp.add_argument("type",
                   metavar="type",
                   choices=["blob", "commit", "tag", "tree"],
                   help="Specify the type")

argsp.add_argument("object",
                   metavar="object",
                   help="The object to display")

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())

def object_find(repo, name, fmt=None, follow=True):
    return name

# the hash-object command
argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute object ID and optionally creates a blob from a file")

argsp.add_argument("-t",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default="blob",
                   help="Specify the type")

argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")

argsp.add_argument("path",
                   help="Read object from <file>")

def cmd_hash_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None

    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

def object_hash(fd, fmt, repo=None):
    """ Hash object, writing it to repo if provided."""
    data = fd.read()

    # Choose constructor according to fmt argument
    if fmt == b'commit':
        obj = GitCommit(data)
    elif fmt == b'tree':
        obj = GitTree(data)
    elif fmt == b'tag':
        obj = GitTag(data)
    elif fmt == b'blob':
        obj = GitBlob(data)
    else:
        raise Exception("Unknown type %s!" % fmt)

    return object_write(obj, repo)

############################################################################################
#---------------------------------- READING COMMIT HISTORY: LOG ---------------------------#
############################################################################################

# parsing commits
