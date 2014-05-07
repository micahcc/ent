#!/usr/bin/python3
 
import sys, paramiko
import getpass 
import re

class Remote:
    client = None
    username = ""
    hostname = ""
    port = 22

    def __init__(self, username, hostname, port = 22):
        """ initializes by parsing a command line ssh://user@host:port/path/ """
        self.username = username
        self.hostname = hostname
        self.port = port

    def start(self, others = [], pw = None):
        if self.client:
            return
        
        print("Username: %s\nHostname: %s\nport: %i" % (self.username, self.hostname, self.port))
        
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()

        if pw:
            try:
                self.client.connect(self.hostname, self.port, self.username, pw)
            except Exception as inst:
                print(type(inst))    # the exception instance
                print(inst.args)     # arguments stored in .args
                print(inst)         
                self.client.close()
        else:
            # try without password
            try:
                self.client.connect(self.hostname, self.port, self.username)
            except paramiko.ssh_exception.PasswordRequiredException:
                # ask for password, to minimize the number of password 
                # re-entries, try the password on all the other passed
                # connections
                pw = getpass.getpass()
                
                for other in others:
                    other.start(pw = pw)
                
                # now try on ourself
                try:
                    self.client.connect(self.hostname, self.port, self.username, pw)
                except Exception as inst:
                    print(type(inst))    # the exception instance
                    print(inst.args)     # arguments stored in .args
                    print(inst)         
                    self.client.close()

            except Exception as inst:
                print(type(inst))    # the exception instance
                print(inst.args)     # arguments stored in .args
                print(inst)         
                self.client.close()

        print("Connected")

    def __exit__(self, type, value, traceback):
        self.clientt.close()

    def run(self, cmd):
        stdin, stdout, stderr = self.client.exec_command(cmd)

    def smartPut(self, local, remote, rmod):
        """ Puts file from some local directory to a remote directory if the 
        file on the remote machine has a modification time different from rmod
        """
        print("put")

    def getD(self, local, remote):
        """ Returns an entire file in memory from the remote server """
        print("get")
    
    def rcopy(self, remote1, remote2):
        print("get")

    def __str__(self):
        out = ""
        if self.username:
            out = out + self.username + "@"
        if self.hostname:
            out = out + self.hostname
        if self.port:
            out = out + ":" + str(self.port)

        return out


#class File:
#    cachename = ""
#    cachesig = ""
#    mainname = ""
#    mainsig = ""
#
#    def mainToCache(self):
#        print("Pushing from main to cache")
#    
#    def cacheToMain(self):
#        print("Pushing from cache to main")
#
#    def updateCacheSig(self):
#        """ Creates a signature from the cache file  If the file doesn't exist,
#        signature set to None """
#        print("Update Cache Signature")
#    
#    def updateMainSig(self):
#        """ Creates a signature from the main file. If the file doesn't exist,
#        signature set to None """
#        print("Update Cache Signature")
#
#
