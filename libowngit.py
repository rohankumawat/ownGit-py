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
# tree -> parent -> author -> committer -> gpgsig -> message
# tree: is a reference to a tree object (the root of the project). it maps blobs IDs to filesystem locations, and describes a state of the work tree.
# parent: is a reference to the parent commit (or commits in the case of a merge commit).
# author and committer: are the people who created and committed the change.
# gpgsig: is a PGP signature of this object.

def kvlm_parse(raw, start=0, dct=None): # key-value list with message
    if not dct:
        dct = collections.OrderedDict()
        # You CANNOT declare the argument as dct=OrderedDict() or all
        # call to the functions will endlessly grow the same dict.

    # This function is recursive: it reads a key/value pair, then call
    # itself back with the new position.  So we first need to know
    # where we are: at a keyword, or already in the messageQ

    # We search for the next space and the next newline.
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)

    # If space appears before newline, we have a keyword.  Otherwise,
    # it's the final message, which we just read to the end of the file.

    # Base case
    # =========
    # If newline appears first (or there's no space at all, in which
    # case find returns -1), we assume a blank line.  A blank line
    # means the remainder of the data is the message.  We store it in
    # the dictionary, with None as the key, and return.
    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start+1:]
        return dct

    # Recursive case
    # ==============
    # we read a key-value pair and recurse for the next.
    key = raw[start:spc]

    # Find the end of the value.  Continuation lines begin with a
    # space, so we loop until we find a "\n" not followed by a space.
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break

    # Grab the value
    # Also, drop the leading space on continuation lines
    value = raw[spc+1:end].replace(b'\n ', b'\n')

    # Don't overwrite existing data contents
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]
    else:
        dct[key]=value

    return kvlm_parse(raw, start=end+1, dct=dct)

def kvlm_serialize(kvlm):
    ret = b''

    # Output fields
    for k in kvlm.keys():
        # Skip the message itself
        if k == None: continue
        val = kvlm[k]
        # Normalize to a list
        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

    # Append message
    ret += b'\n' + kvlm[None] + b'\n'

    return 

# commit object
class GitCommit(GitObject):
    fmt=b'commit'

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)

    def init(self):
        self.kvlm = dict()

# log command
argsp = argsubparsers.add_parser("log", help="Display history of a given commit.")
argsp.add_argument("commit",
                   default="HEAD",
                   nargs="?",
                   help="Commit to start at.")

def cmd_log(args):
    repo = repo_find()

    print("digraph wyaglog{")
    print("  node[shape=rect]")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def log_graphviz(repo, sha, seen):

    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo, sha)
    short_hash = sha[0:8]
    message = commit.kvlm[None].decode("utf8").strip()
    message = message.replace("\\", "\\\\")
    message = message.replace("\"", "\\\"")

    if "\n" in message: # Keep only the first line
        message = message[:message.index("\n")]

    print("  c_{0} [label=\"{1}: {2}\"]".format(sha, sha[0:7], message))
    assert commit.fmt==b'commit'

    if not b'parent' in commit.kvlm.keys():
        # Base case: the initial commit.
        return

    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")
        print ("  c_{0} -> c_{1};".format(sha, p))
        log_graphviz(repo, p, seen)

############################################################################################
#---------------------------------- READING COMMIT DATA: CHECKOUT -------------------------#
############################################################################################

class GitTreeLeaf (object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

def tree_parse_one(raw, start=0):
    # Find the space terminator of the mode
    x = raw.find(b' ', start)
    assert x-start == 5 or x-start==6

    # Read the mode
    mode = raw[start:x]
    if len(mode) == 5:
        # Normalize to six bytes.
        mode = b" " + mode

    # Find the NULL terminator of the path
    y = raw.find(b'\x00', x)
    # and read the path
    path = raw[x+1:y]

    # Read the SHA and convert to a hex string
    sha = format(int.from_bytes(raw[y+1:y+21], "big"), "040x")
    return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)

def tree_parse(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)

    return ret

# Notice this isn't a comparison function, but a conversion function.
# Python's default sort doesn't accept a custom comparison function,
# like in most languages, but a `key` arguments that returns a new
# value, which is compared using the default rules.  So we just return
# the leaf name, with an extra / if it's a directory.
def tree_leaf_sort_key(leaf):
    if leaf.mode.startswith(b"10"):
        return leaf.path
    else:
        return leaf.path + "/"

def tree_serialize(obj):
    obj.items.sort(key=tree_leaf_sort_key)
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path.encode("utf8")
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")
    return ret
    
class GitTree(GitObject):
    fmt=b'tree'

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)

    def init(self):
        self.items = list()

argsp = argsubparsers.add_parser("ls-tree", help="Pretty-print a tree object.")
argsp.add_argument("-r",
                   dest="recursive",
                   action="store_true",
                   help="Recurse into sub-trees")

argsp.add_argument("tree",
                   help="A tree-ish object.")

def cmd_ls_tree(args):
    repo = repo_find()
    ls_tree(repo, args.tree, args.recursive)

def ls_tree(repo, ref, recursive=None, prefix=""):
    sha = object_find(repo, ref, fmt=b"tree")
    obj = object_read(repo, sha)
    for item in obj.items:
        if len(item.mode) == 5:
            type = item.mode[0:1]
        else:
            type = item.mode[0:2]

        match type: # Determine the type.
            case b'04': type = "tree"
            case b'10': type = "blob" # A regular file.
            case b'12': type = "blob" # A symlink. Blob contents is link target.
            case b'16': type = "commit" # A submodule
            case _: raise Exception("Weird tree leaf mode {}".format(item.mode))

        if not (recursive and type=='tree'): # This is a leaf
            print("{0} {1} {2}\t{3}".format(
                "0" * (6 - len(item.mode)) + item.mode.decode("ascii"),
                # Git's ls-tree displays the type
                # of the object pointed to.  We can do that too :)
                type,
                item.sha,
                os.path.join(prefix, item.path)))
        else: # This is a branch, recurse
            ls_tree(repo, item.sha, recursive, os.path.join(prefix, item.path))

# git checkout
argsp = argsubparsers.add_parser("checkout", help="Checkout a commit inside of a directory.")

argsp.add_argument("commit",
                   help="The commit or tree to checkout.")

argsp.add_argument("path",
                   help="The EMPTY directory to checkout on.")

def cmd_checkout(args):
    repo = repo_find()

    obj = object_read(repo, object_find(repo, args.commit))

    # If the object is a commit, we grab its tree
    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

    # Verify that path is an empty directory
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception("Not a directory {0}!".format(args.path))
        if os.listdir(args.path):
            raise Exception("Not empty {0}!".format(args.path))
    else:
        os.makedirs(args.path)

    tree_checkout(repo, obj, os.path.realpath(args.path))

def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            # @TODO Support symlinks (identified by mode 12****)
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)


############################################################################################
#---------------------------------- REFS, TAGS & BRANCHES ---------------------------------#
############################################################################################

# references
def ref_resolve(repo, ref):
    path = repo_file(repo, ref)

    # Sometimes, an indirect reference may be broken.  This is normal
    # in one specific case: we're looking for HEAD on a new repository
    # with no commits.  In that case, .git/HEAD points to "ref:
    # refs/heads/main", but .git/refs/heads/main doesn't exist yet
    # (since there's no commit for it to refer to).
    if not os.path.isfile(path):
        return None

    with open(path, 'r') as fp:
        data = fp.read()[:-1]
        # Drop final \n ^^^^^
    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    else:
        return data

def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    ret = collections.OrderedDict()
    # Git shows refs sorted.  To do the same, we use
    # an OrderedDict and sort the output of listdir
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)
        else:
            ret[f] = ref_resolve(repo, can)

    return ret

argsp = argsubparsers.add_parser("show-ref", help="List references.")

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
    for k, v in refs.items():
        if type(v) == str:
            print ("{0}{1}{2}".format(
                v + " " if with_hash else "",
                prefix + "/" if prefix else "",
                k))
        else:
            show_ref(repo, v, with_hash=with_hash, prefix="{0}{1}{2}".format(prefix, "/" if prefix else "", k))

# tags
class GitTag(GitCommit):
    fmt = b'tag'

argsp = argsubparsers.add_parser(
    "tag",
    help="List and create tags")

argsp.add_argument("-a",
                   action="store_true",
                   dest="create_tag_object",
                   help="Whether to create a tag object")

argsp.add_argument("name",
                   nargs="?",
                   help="The new tag's name")

argsp.add_argument("object",
                   default="HEAD",
                   nargs="?",
                   help="The object the new tag will point to")

def cmd_tag(args):
    repo = repo_find()

    if args.name:
        tag_create(repo,
                   args.name,
                   args.object,
                   type="object" if args.create_tag_object else "ref")
    else:
        refs = ref_list(repo)
        show_ref(repo, refs["tags"], with_hash=False)

def tag_create(repo, name, ref, create_tag_object=False):
    # get the GitObject from the object reference
    sha = object_find(repo, ref)

    if create_tag_object:
        # create tag object (commit)
        tag = GitTag(repo)
        tag.kvlm = collections.OrderedDict()
        tag.kvlm[b'object'] = sha.encode()
        tag.kvlm[b'type'] = b'commit'
        tag.kvlm[b'tag'] = name.encode()
        # Feel free to let the user give their name!
        # Notice you can fix this after commit, read on!
        tag.kvlm[b'tagger'] = b'Wyag <wyag@example.com>'
        # …and a tag message!
        tag.kvlm[None] = b"A tag generated by wyag, which won't let you customize the message!"
        tag_sha = object_write(tag)
        # create reference
        ref_create(repo, "tags/" + name, tag_sha)
    else:
        # create lightweight tag (ref)
        ref_create(repo, "tags/" + name, sha)

def ref_create(repo, ref_name, sha):
    with open(repo_file(repo, "refs/" + ref_name), 'w') as fp:
        fp.write(sha + "\n")

# referring to objects
# the "object_find" function

def object_resolve(repo, name):
    """Resolve name to an object hash in repo.

This function is aware of:

 - the HEAD literal
    - short and long hashes
    - tags
    - branches
    - remote branches"""
    candidates = list()
    hashRE = re.compile(r"^[0-9A-Fa-f]{4,40}$")

    # Empty string?  Abort.
    if not name.strip():
        return None

    # Head is nonambiguous
    if name == "HEAD":
        return [ ref_resolve(repo, "HEAD") ]

    # If it's a hex string, try for a hash.
    if hashRE.match(name):
        # This may be a hash, either small or full.  4 seems to be the
        # minimal length for git to consider something a short hash.
        # This limit is documented in man git-rev-parse
        name = name.lower()
        prefix = name[0:2]
        path = repo_dir(repo, "objects", prefix, mkdir=False)
        if path:
            rem = name[2:]
            for f in os.listdir(path):
                if f.startswith(rem):
                    # Notice a string startswith() itself, so this
                    # works for full hashes.
                    candidates.append(prefix + f)

    # Try for references.
    as_tag = ref_resolve(repo, "refs/tags/" + name)
    if as_tag: # Did we find a tag?
        candidates.append(as_tag)

    as_branch = ref_resolve(repo, "refs/heads/" + name)
    if as_branch: # Did we find a branch?
        candidates.append(as_branch)

    return candidates


def object_find(repo, name, fmt=None, follow=True):
      sha = object_resolve(repo, name)

      if not sha:
          raise Exception("No such reference {0}.".format(name))

      if len(sha) > 1:
          raise Exception("Ambiguous reference {0}: Candidates are:\n - {1}.".format(name,  "\n - ".join(sha)))

      sha = sha[0]

      if not fmt:
          return sha

      while True:
          obj = object_read(repo, sha)
          #     ^^^^^^^^^^^ < this is a bit agressive: we're reading
          # the full object just to get its type.  And we're doing
          # that in a loop, albeit normally short.  Don't expect
          # high performance here.

          if obj.fmt == fmt:
              return sha

          if not follow:
              return None

          # Follow tags
          if obj.fmt == b'tag':
                sha = obj.kvlm[b'object'].decode("ascii")
          elif obj.fmt == b'commit' and fmt == b'tree':
                sha = obj.kvlm[b'tree'].decode("ascii")
          else:
              return None

# the rev-parse command
argsp = argsubparsers.add_parser(
    "rev-parse",
    help="Parse revision (or other objects) identifiers")

argsp.add_argument("--wyag-type",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default=None,
                   help="Specify the expected type")

argsp.add_argument("name",
                   help="The name to parse")

def cmd_rev_parse(args):
    if args.type:
        fmt = args.type.encode()
    else:
        fmt = None

    repo = repo_find()

    print (object_find(repo, args.name, fmt, follow=True))

############################################################################################
#---------------------------------- STAGING AREA & INDEX ----------------------------------#
############################################################################################

# the index file
# most complicated piece of data a Git repository can hold.
# it is made of three parts:
# 1. a header (with the format version number and the number of entries the index holds)
# 2. a series of entries, sorted, each representing a file in the repository (padded to multiples of 8 bytes)
# 3. a series of optional extensions

# a single entry:
"""
It’s worth observing that an entry stores both the SHA-1 of the associated blob in the object store and a ton of metadata about the actual file on the actual filesystem. 
Again, this is because git/wyag status will need to determine which files in the index were modified: it is much more efficient to begin by checking the last-modified 
timestamp and comparing it with a known values, before comparing actual files.
"""
class GitIndexEntry (object):
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None,
                 mode_type=None, mode_perms=None, uid=None, gid=None,
                 fsize=None, sha=None, flag_assume_valid=None,
                 flag_stage=None, name=None):
      # The last time a file's metadata changed.  This is a pair
      # (timestamp in seconds, nanoseconds)
      self.ctime = ctime
      # The last time a file's data changed.  This is a pair
      # (timestamp in seconds, nanoseconds)
      self.mtime = mtime
      # The ID of device containing this file
      self.dev = dev
      # The file's inode number
      self.ino = ino
      # The object type, either b1000 (regular), b1010 (symlink),
      # b1110 (gitlink).
      self.mode_type = mode_type
      # The object permissions, an integer.
      self.mode_perms = mode_perms
      # User ID of owner
      self.uid = uid
      # Group ID of ownner
      self.gid = gid
      # Size of this object, in bytes
      self.fsize = fsize
      # The object's SHA
      self.sha = sha
      self.flag_assume_valid = flag_assume_valid
      self.flag_stage = flag_stage
      # Name of the object (full path this time!)
      self.name = name

# index file is a binary file
class GitIndex (object):
    version = None
    entries = []
    # ext = None
    # sha = None

    def __init__(self, version=2, entries=None):
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries

def index_read(repo):
    index_file = repo_file(repo, "index")

    # New repositories have no index!
    if not os.path.exists(index_file):
        return GitIndex()

    with open(index_file, 'rb') as f:
        raw = f.read()

    header = raw[:12]
    signature = header[:4]
    assert signature == b"DIRC" # Stands for "DirCache"
    version = int.from_bytes(header[4:8], "big")
    assert version == 2, "wyag only supports index file version 2"
    count = int.from_bytes(header[8:12], "big")

    entries = list()

    content = raw[12:]
    idx = 0
    for i in range(0, count):
        # Read creation time, as a unix timestamp (seconds since
        # 1970-01-01 00:00:00, the "epoch")
        ctime_s =  int.from_bytes(content[idx: idx+4], "big")
        # Read creation time, as nanoseconds after that timestamps,
        # for extra precision.
        ctime_ns = int.from_bytes(content[idx+4: idx+8], "big")
        # Same for modification time: first seconds from epoch.
        mtime_s = int.from_bytes(content[idx+8: idx+12], "big")
        # Then extra nanoseconds
        mtime_ns = int.from_bytes(content[idx+12: idx+16], "big")
        # Device ID
        dev = int.from_bytes(content[idx+16: idx+20], "big")
        # Inode
        ino = int.from_bytes(content[idx+20: idx+24], "big")
        # Ignored.
        unused = int.from_bytes(content[idx+24: idx+26], "big")
        assert 0 == unused
        mode = int.from_bytes(content[idx+26: idx+28], "big")
        mode_type = mode >> 12
        assert mode_type in [0b1000, 0b1010, 0b1110]
        mode_perms = mode & 0b0000000111111111
        # User ID
        uid = int.from_bytes(content[idx+28: idx+32], "big")
        # Group ID
        gid = int.from_bytes(content[idx+32: idx+36], "big")
        # Size
        fsize = int.from_bytes(content[idx+36: idx+40], "big")
        # SHA (object ID).  We'll store it as a lowercase hex string
        # for consistency.
        sha = format(int.from_bytes(content[idx+40: idx+60], "big"), "040x")
        # Flags we're going to ignore
        flags = int.from_bytes(content[idx+60: idx+62], "big")
        # Parse flags
        flag_assume_valid = (flags & 0b1000000000000000) != 0
        flag_extended = (flags & 0b0100000000000000) != 0
        assert not flag_extended
        flag_stage =  flags & 0b0011000000000000
        # Length of the name.  This is stored on 12 bits, some max
        # value is 0xFFF, 4095.  Since names can occasionally go
        # beyond that length, git treats 0xFFF as meaning at least
        # 0xFFF, and looks for the final 0x00 to find the end of the
        # name --- at a small, and probably very rare, performance
        # cost.
        name_length = flags & 0b0000111111111111

        # We've read 62 bytes so far.
        idx += 62

        if name_length < 0xFFF:
            assert content[idx + name_length] == 0x00
            raw_name = content[idx:idx+name_length]
            idx += name_length + 1
        else:
            print("Notice: Name is 0x{:X} bytes long.".format(name_length))
            # This probably wasn't tested enough.  It works with a
            # path of exactly 0xFFF bytes.  Any extra bytes broke
            # something between git, my shell and my filesystem.
            null_idx = content.find(b'\x00', idx + 0xFFF)
            raw_name = content[idx: null_idx]
            idx = null_idx + 1

        # Just parse the name as utf8.
        name = raw_name.decode("utf8")

        # Data is padded on multiples of eight bytes for pointer
        # alignment, so we skip as many bytes as we need for the next
        # read to start at the right position.

        idx = 8 * ceil(idx / 8)

        # And we add this entry to our list.
        entries.append(GitIndexEntry(ctime=(ctime_s, ctime_ns),
                                     mtime=(mtime_s,  mtime_ns),
                                     dev=dev,
                                     ino=ino,
                                     mode_type=mode_type,
                                     mode_perms=mode_perms,
                                     uid=uid,
                                     gid=gid,
                                     fsize=fsize,
                                     sha=sha,
                                     flag_assume_valid=flag_assume_valid,
                                     flag_stage=flag_stage,
                                     name=name))

    return GitIndex(version=version, entries=entries)

# ls-files command
argsp = argsubparsers.add_parser("ls-files", help = "List all the stage files")
argsp.add_argument("--verbose", action="store_true", help="Show everything.")

def cmd_ls_files(args):
  repo = repo_find()
  index = index_read(repo)
  if args.verbose:
    print("Index file format v{}, containing {} entries.".format(index.version, len(index.entries)))

  for e in index.entries:
    print(e.name)
    if args.verbose:
      print("  {} with perms: {:o}".format(
        { 0b1000: "regular file",
          0b1010: "symlink",
          0b1110: "git link" }[e.mode_type],
        e.mode_perms))
      print("  on blob: {}".format(e.sha))
      print("  created: {}.{}, modified: {}.{}".format(
        datetime.fromtimestamp(e.ctime[0])
        , e.ctime[1]
        , datetime.fromtimestamp(e.mtime[0])
        , e.mtime[1]))
      print("  device: {}, inode: {}".format(e.dev, e.ino))
      print("  user: {} ({})  group: {} ({})".format(
        pwd.getpwuid(e.uid).pw_name,
        e.uid,
        grp.getgrgid(e.gid).gr_name,
        e.gid))
      print("  flags: stage={} assume_valid={}".format(
        e.flag_stage,
        e.flag_assume_valid))
      
 # check-ignore command
argsp = argsubparsers.add_parser("check-ignore", help = "Check path(s) against ignore rules.")
argsp.add_argument("path", nargs="+", help="Paths to check")

def cmd_check_ignore(args):
  repo = repo_find()
  rules = gitignore_read(repo)
  for path in args.path:
      if check_ignore(rules, path):
        print(path)

def gitignore_parse1(raw):
    raw = raw.strip() # Remove leading/trailing spaces

    if not raw or raw[0] == "#":
        return None
    elif raw[0] == "!":
        return (raw[1:], False)
    elif raw[0] == "\\":
        return (raw[1:], True)
    else:
        return (raw, True)

def gitignore_parse(lines):
    ret = list()

    for line in lines:
        parsed = gitignore_parse1(line)
        if parsed:
            ret.append(parsed)

    return ret

class GitIgnore(object):
    absolute = None
    scoped = None

    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped

def gitignore_read(repo):
    ret = GitIgnore(absolute=list(), scoped=dict())

    # Read local configuration in .git/info/exclude
    repo_file = os.path.join(repo.gitdir, "info/exclude")
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    # Global configuration
    if "XDG_CONFIG_HOME" in os.environ:
        config_home = os.environ["XDG_CONFIG_HOME"]
    else:
        config_home = os.path.expanduser("~/.config")
    global_file = os.path.join(config_home, "git/ignore")

    if os.path.exists(global_file):
        with open(global_file, "r") as f:
            ret.absolute.append(gitignore_parse(f.readlines()))

    # .gitignore files in the index
    index = index_read(repo)

    for entry in index.entries:
        if entry.name == ".gitignore" or entry.name.endswith("/.gitignore"):
            dir_name = os.path.dirname(entry.name)
            contents = object_read(repo, entry.sha)
            lines = contents.blobdata.decode("utf8").splitlines()
            ret.scoped[dir_name] = gitignore_parse(lines)
    return ret

def check_ignore1(rules, path):
    result = None
    for (pattern, value) in rules:
        if fnmatch(path, pattern):
            result = value
    return result

def check_ignore_scoped(rules, path):
    parent = os.path.dirname(path)
    while True:
        if parent in rules:
            result = check_ignore1(rules[parent], path)
            if result != None:
                return result
        if parent == "":
            break
        parent = os.path.dirname(parent)
    return None

def check_ignore_absolute(rules, path):
    parent = os.path.dirname(path)
    for ruleset in rules:
        result = check_ignore1(ruleset, path)
        if result != None:
            return result
    return False # This is a reasonable default at this point.

def check_ignore(rules, path):
    if os.path.isabs(path):
        raise Exception("This function requires path to be relative to the repository's root")

    result = check_ignore_scoped(rules.scoped, path)
    if result != None:
        return result

    return check_ignore_absolute(rules.absolute, path)