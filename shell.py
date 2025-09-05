import os
import getpass
import socket
import shlex

def getrelativepathstr(path: str):
    return path.replace(os.path.expanduser("~"), "~")

def main():
    uname = getpass.getuser()
    hostname = socket.gethostname()

    while True:
        cwd = os.getcwd()
        inp = input(uname + "@" + hostname + ":" + getrelativepathstr(cwd) + "$ ").strip()

        if inp == "exit":
            break
        elif inp == "":
            continue

        try:
            args = shlex.split(inp)
        except Exception as err:
            print("Parser error:", err)
            continue

        if args[0] == "cd":
            # TODO: Implement
            print("cd", args[1:])
                
        elif args[0] == "ls":
            # TODO: Implement
            print("ls", args[1:])


main()
