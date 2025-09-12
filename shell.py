import os
import getpass
import socket
import shlex
import argparse
import sys
from xml.parsers import expat
from base64 import b64decode

import traceback

class VFS:
    filesystem = {}
    using_vfs = False
    cwd = None

class VFSBuild:
    cur_dir = None
    cur_filename = None
    dir_traceback = []

    def XMLStartElemHandler(name, attr):
        if name == "rootdir":
            VFS.filesystem = {}
            VFSBuild.cur_dir = VFS.filesystem
            return
        elif VFSBuild.cur_dir == None:
            return

        if name == "dir":
            VFSBuild.cur_dir[attr["name"]] = {}
            VFSBuild.dir_traceback.append(VFSBuild.cur_dir)
            VFSBuild.cur_dir = VFSBuild.cur_dir[attr["name"]]
        elif name == "file" and VFSBuild.cur_filename == None:
            VFSBuild.cur_dir[attr["name"]] = ""
            VFSBuild.cur_filename = attr["name"]
    
    def XMLChDataHandler(data):
        if VFSBuild.cur_filename:
            VFSBuild.cur_dir[VFSBuild.cur_filename] = data
    
    def XMLEndElemHandler(name):
        if name == "dir":
            VFSBuild.cur_dir = VFSBuild.dir_traceback.pop()
        elif name == "file":
            VFSBuild.cur_filename = None
        elif name == "rootdir":
            VFSBuild.cur_dir = None


def getrelativepathstr(path: str):
    return path.replace(os.path.expanduser("~"), "~")

def buildvfs(path: str):
    VFS.using_vfs = True

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
    
    print("[VFS] Built:", VFS.filesystem)

def processcommand(cmd: str):
    try:
        args = shlex.split(cmd)
    except Exception as err:
        print("Parser error:", err)
        return
    
    #print("!processing:", args)

    if args[0] == "cd":
        # TODO: Implement
        print("cd", args[1:])   
        
    elif args[0] == "ls":
        # TODO: Implement
        print("ls", args[1:])

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--vfs", help="set absolute or relative path to VFS file")
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

    
    print("\n--------------------------------------")
    print("CONFIG:")
    print("VFS:", vfs)
    print("Start Script:", startscript)
    print("--------------------------------------\n")

    if vfs:
        buildvfs(vfs)

    if startscript:
        execscript(startscript)

    uname = getpass.getuser()
    hostname = socket.gethostname()

    while True:
        cwd = os.getcwd()
        inp = input(uname + "@" + hostname + ":" + getrelativepathstr(cwd) + "$ ").strip()

        if inp == "exit":
            break

        processcommand(inp)


main()