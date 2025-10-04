import os
import getpass
import socket
import shlex
import argparse
import sys
import time
import psutil
import math
from xml.parsers import expat
from base64 import b64decode

import traceback

class Shell:
    allow_switchfs = False
    is_running = True

class FSElemDoesntExistException(Exception):
    def __init__(self):
        super().__init__()

class FSElement:
    def __init__(self, name, is_directory, parent):
        self.name = name
        self.is_directory: bool = is_directory
        self.parent: FSElement | None = parent
        if is_directory:
            self.contents = {}
        else:
            self.contents = ""

    def __getitem__(self, key):
        return self.contents[key]
    
    def __setitem__(self, key, value):
        if not self.is_directory:
            raise Exception("Attemting to rewrite file contents string with index")
        self.contents[key] = value

    def __str__(self):
        return str(self.contents)

class VFS:
    filesystem = FSElement("", True, None)
    cwd = filesystem
    is_ready = False

    def isDirElem(elem: FSElement):
        if type(elem) != FSElement:
            raise FSElemDoesntExistException
        return elem.is_directory
    
    def isDir(path: str):
        elem = VFS.getByPath(path)
        return VFS.isDirElem(elem)
    
    def getAbsPath(elem: FSElement):
        result = elem.name

        if elem.parent:
            elem = elem.parent

            while elem.parent:
                result = elem.name + "/" + result
                elem = elem.parent
        
        result = "/" + result

        return result
    
    def getByRelativePath(root_dir: FSElement, path: str):
        curfile: FSElement = root_dir

        lspath = path.split("/")
        for nextdirname in lspath:
            try:
                #print(nextdirname)
                assert VFS.isDirElem(curfile)

                if not nextdirname: continue

                if nextdirname == "..":
                    curfile = curfile.parent if curfile.parent else curfile
                elif nextdirname != ".":
                    curfile = curfile[nextdirname]
            except Exception:
                return None
        
        return curfile

    def getByPath(path: str):
        if path == ".":
            return VFS.cwd
        
        if len(path) > 1 and path[-1] == "/":
            path = path[:-1]
        
        if path[0] == "/":
            if len(path) == 1:
                return VFS.filesystem

            return VFS.getByRelativePath(VFS.filesystem, path[1:])
        else:
            return VFS.getByRelativePath(VFS.cwd, path)
    
    def listDir(path):
        elem = VFS.getByPath(path) if path else VFS.cwd
        assert VFS.isDirElem(elem), Exception(path + " is not a directory")
        return list(elem.contents.keys())

class VFSBuild:
    cur_dir: FSElement | None = None
    cur_filename: FSElement | None = None
    dir_traceback = []

    def XMLStartElemHandler(name, attr):
        if name == "rootdir":
            VFS.filesystem = FSElement("", True, None)
            
            VFSBuild.cur_dir = VFS.filesystem
            return
        elif VFSBuild.cur_dir == None:
            return

        if name == "dir":
            newdir = FSElement(attr["name"], True, VFSBuild.cur_dir)
            VFSBuild.cur_dir[attr["name"]] = newdir
            VFSBuild.dir_traceback.append(VFSBuild.cur_dir)
            VFSBuild.cur_dir = VFSBuild.cur_dir[attr["name"]]

        elif name == "file" and VFSBuild.cur_filename == None:
            newfile = FSElement(attr["name"], False, VFSBuild.cur_dir)
            VFSBuild.cur_dir[attr["name"]] = newfile
            VFSBuild.cur_filename = attr["name"]
        
        else:
            print("[VFS] Warning: unrecognized filesystem element:", name)
    
    def XMLChDataHandler(data):
        if VFSBuild.cur_filename and VFSBuild.cur_dir:
            VFSBuild.cur_dir[VFSBuild.cur_filename].contents = data
    
    def XMLEndElemHandler(name):
        if name == "dir":
            VFSBuild.cur_dir = VFSBuild.dir_traceback.pop()
        elif name == "file":
            VFSBuild.cur_filename = None
        elif name == "rootdir":
            VFSBuild.cur_dir = None

class Command:
    _using_vfs = False
    _cmd_tbl = {}

    _proc_st_time = psutil.Process(os.getpid()).create_time()

    def _cd_realfs(args):
        if not args:
            print("Error: no path given")
            return

        try:
            os.chdir(os.path.expanduser(args[0]))
        except Exception as err:
            print("Error:", err)
    
    def _lsuniversal(args, lsfunc):
        if len(args) > 1:
            for arg in args:
                try:
                    dirlist = lsfunc(arg)

                    print("")
                    print(arg, ":", sep="")
                    print(*dirlist, sep="\n")
                except FSElemDoesntExistException:
                    print("Error:", arg, "doesn't exist")
                except Exception as e:
                    print("Error:", e)
        else:
            try:
                print(*lsfunc(args[0] if args else None), sep="\n")
            except FSElemDoesntExistException:
                print("Error:", args[0] if args else "current directory (?)", "doesn't exist")
            except Exception as e:
                print("Error:", e)
        
    def _ls_realfs(args):
        Command._lsuniversal(args, os.listdir)
    
    def _treeprint(path, lsfunc, isdirfunc):
        if path[-1] == "/":
            path = path[0:-1]
        stack = [[path + "/" + s for s in lsfunc(path + "/")]]

        print(path[path.rfind("/")+1:] if path else "/")
        while stack:
            #print(stack)
            if stack[-1] == []:
                stack.pop()
                continue

            file = stack[-1].pop(0)

            #print(file)
            print("\u2502", end="")
            print("   \u2502" * (len(stack) - 1), end="")
            print("\b\u251c", file[file.rfind("/")+1:])

            if isdirfunc(file):
                stack.append([file + "/" + s for s in lsfunc(file)])
    
    def _treeparseandexec(args: list, lsfunc, isdirfunc):
        if args:
            while args:
                path = args.pop(0)
                try:
                    assert isdirfunc(path), path + " is not a directory"
                    Command._treeprint(path, lsfunc, isdirfunc)
                except FSElemDoesntExistException:
                    print("Error:", path, "doesn't exist")
                except Exception as e:
                    print("Error:", e)
        else:
            Command._treeprint(".", lsfunc, isdirfunc)
    
    def _tree_realfs(args: list):
        Command._treeparseandexec(args, os.listdir, os.path.isdir)
    
    def _cat_realfs(args):
        for arg in args:
            try:
                with open(arg) as f:
                    print(*f.readlines(), sep="")
            except Exception as e:
                print("Error:", e)


    def _cd_vfs(args):
        if not args:
            print("Error: no path given")
            return
        
        wd = VFS.getByPath(args[0])
        if wd and VFS.isDirElem(wd):
            VFS.cwd = wd
        else:
            print("Error:", args[0], " doesn't exist or is a file")

    def _ls_vfs(args):
        Command._lsuniversal(args, VFS.listDir)
    
    def _tree_vfs(args):
        Command._treeparseandexec(args, VFS.listDir, VFS.isDir)

    def _cat_vfs(args):
        for arg in args:
            try:
                curfile = VFS.getByPath(arg)
                assert not VFS.isDirElem(curfile), arg + " is a directory"
                print(curfile.contents, sep="")
            except FSElemDoesntExistException:
                print("Error:", arg, "doesn't exist")
            except Exception as e:
                print("Error:", e)
    

    def _uptime(args):
        loctime = time.localtime()
        uptime_str = secondstohms(math.floor(time.time() - Command._proc_st_time))

        print(time.strftime("%H:%M:%S", loctime), "up", uptime_str)


    _cmd_tbl["cd"] = _cd_realfs
    _cmd_tbl["ls"] = _ls_realfs
    _cmd_tbl["tree"] = _tree_realfs
    _cmd_tbl["cat"] = _cat_realfs

    _cmd_tbl["uptime"] = _uptime
    
    def setUsingVFS(using_vfs):
        if Command._using_vfs == using_vfs: return

        if using_vfs and not VFS.is_ready:
            raise Exception("VFS is not ready")

        if using_vfs:
            Command._cmd_tbl["cd"] = Command._cd_vfs
            Command._cmd_tbl["ls"] = Command._ls_vfs
            Command._cmd_tbl["tree"] = Command._tree_vfs
            Command._cmd_tbl["cat"] = Command._cat_vfs
        else:
            Command._cmd_tbl["cd"] = Command._cd_realfs
            Command._cmd_tbl["ls"] = Command._ls_realfs
            Command._cmd_tbl["tree"] = Command._tree_realfs
            Command._cmd_tbl["cat"] = Command._cat_realfs

        Command._using_vfs = using_vfs
    
    def getUsingVFS():
        return Command._using_vfs
    
    def run(args):
        cmd = args[0]
        
        if cmd in Command._cmd_tbl:
            Command._cmd_tbl[cmd](args[1:])
        else:
            print("Error: command", cmd, "not found")
    

def secondstohms(sec):
    m = math.floor(sec / 60)
    sec = sec - m * 60

    h = math.floor(m / 60)
    m = m - h * 60

    return f"{h:02}:{m:02}:{sec:02}"

def getexpanduserstr(path: str):
    return path.replace(os.path.expanduser("~"), "~")

def buildvfs(path: str):
    has_errors = False

    parser = expat.ParserCreate()

    parser.StartElementHandler = VFSBuild.XMLStartElemHandler
    parser.EndElementHandler = VFSBuild.XMLEndElemHandler
    parser.CharacterDataHandler = VFSBuild.XMLChDataHandler

    try:
        with open(path, 'rb') as f:
            head = f.read(5)
            f.seek(0, os.SEEK_SET)

            if head == b'<?xml':
                
                parser.ParseFile(f)
            else:
                b64 = f.read()
                s = b64decode(b64)
                parser.Parse(s)
    except Exception:
        print("[VFS!!!] ERROR:", traceback.format_exc())
        has_errors = True
    
    if not has_errors:
        print("[VFS] Built!")
    else:
        print("VFS] Built with Errors!")

    VFS.cwd = VFS.filesystem
    VFS.is_ready = True

    Command.setUsingVFS(True)

def processcommand(cmd: str):
    if cmd == "exit":
        Shell.is_running = False
        return
    elif cmd == "switchfs" and Shell.allow_switchfs:
        try:
            curmode = not Command.getUsingVFS()
            Command.setUsingVFS(curmode)
            modestr = "VFS" if curmode else "real FS"
            print("Shell is now working in ::", modestr, ":: mode", sep="")
        except Exception as e:
            print("Error:", e)

        return
    
    try:
        args = shlex.split(cmd)
    except Exception as err:
        print("Parser error:", err)
        return
    
    #print("!processing:", args)

    Command.run(args)

def execscript(path: str):
    with open(path) as scr:
        #print("Executing script:", path)

        for line in [line.strip() for line in scr.readlines()]:
            if line == "" or line[0] == "#": continue

            print("$", line)

            if line == "exit":
                break

            processcommand(line)

def findfile(path):
    path = os.path.expanduser(path)

    if os.path.isfile(path):
        if os.path.isabs(path):
            return path
        else:
            return os.getcwd() + '/' + path
    else:
        return ""

def main():
    parser = argparse.ArgumentParser(description="Shell emulator written in Python")
    parser.add_argument("--vfs", help="set absolute or relative path to VFS file")
    parser.add_argument("-s", "--switchfs", action="store_true", help="allow switching between VFS and real FS using \"switchfs\" command")
    parser.add_argument("--script", help="set absolute or relative path to Start Script")

    cmdargs = vars(parser.parse_args(sys.argv[1:]))

    vfs = findfile(cmdargs["vfs"]) if cmdargs["vfs"] else None
    startscript = findfile(cmdargs["script"]) if cmdargs["script"] else None

    if vfs == "":
        print("[!!!] Could not find VFS file with path:", cmdargs["vfs"])
        vfs = None

    if startscript == "":
        print("[!!!] Could not find Start Script with path:", cmdargs["script"])
        startscript = None
    
    if cmdargs["switchfs"]:
        Shell.allow_switchfs = True
    
    print("\n--------------------------------------")
    print("CONFIG:")
    print("VFS:", vfs)
    print("Allow switching FS mode:", cmdargs["switchfs"])
    print("Start Script:", startscript)
    print("--------------------------------------\n")

    if vfs:
        buildvfs(vfs)

    if startscript:
        execscript(startscript)

    uname = getpass.getuser()
    hostname = socket.gethostname()

    print("")

    while Shell.is_running:
        if Command.getUsingVFS():
            cwd = VFS.getAbsPath(VFS.cwd)
        else:
            cwd = os.getcwd()
        
        inp = input(uname + "@" + hostname + ":" + getexpanduserstr(cwd) + "$ ").strip()

        processcommand(inp)


main()