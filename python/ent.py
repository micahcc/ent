import os, time
import re
import copy
import sys 

"""
Main Data Structures:
    Ent: Parser and Global Class

    Ring: Hold a concrete set of Command Line Arguments, input and output files

    Branch: Generator of Rings

    File: Holds a file name knowns which ring generates it
"""

gvarre = re.compile('(.*?)\${\s*(.*?)\s*}(.*)')
VERBOSE=10

def parseURI(uri):
    urire = re.compile("^\s*(ssh)://(?:([a-z_][a-z0-9_]{0,30})@)?([a-zA-Z.-]*)"\
            "(?:([0-9]+))?(/.*)?")
    rmatch = urire.search(uri)
    if not rmatch:
        return (None, None, None, None, uri)

    proto = rmatch.group(1)
    ruser = rmatch.group(2)
    rhost = rmatch.group(3)
    if rmatch.group(4):
        rport = int(rmatch.group(4))
    else:
        rport = 22
    rpath = rmatch.group(5)
    return (proto,ruser, rhost, rport, rpath)

class InputError(Exception):
    """Exception raised for errors in the input.
       Attributes:
       expr -- input expression in which the error occurred
       msg  -- explanation of the error
    """
                                    
    def __init__(self, expr, msg):
        self.expr = expr
        self.msg = msg

##
# @brief Parses a string with ${VARNAME} type syntax with the contents of
# defs. If a variable contains more variable those are resolved as well. 
# Special definitions:
# ${<} replaced with all inputs
# ${<N} where N is >= 0, replaced the the N'th input
# ${>} replaced with all outputs
# ${>N} where N is >= 0, replaced the the N'th output
# ${*SEP*VARNAME} 
#
# @param inputs List of Files
# @param outputs List of List of Files
# @param defs Global variables to check
#
# @return 
def expand(string, inputs, outputs, defs):
    # $> - 0 - all outputs
    # $< - 1 - all inputs
    # ${>#} - 2 - output number outputs
    # ${<#} - 3 - output number outputs
    # ${*SEP*VARNAME} - 4,5 - expand VARNAME, separating them by SEP
    # ${VARNAME} - 6 - expand varname

    allout  = "(\$>|\${>})|"
    allin   = "(\$<|\${<})|"
    singout = "\${>\s*([0-9]*)}|"
    singin  = "\${<\s*([0-9]*)}|"
    sepvar  = "\${\*([^*]*)\*([^}]*)}|"
    regvar  = "\${([^}]*)}"
    r = re.compile(allout+allin+singout+singin+sepvar+regvar)
    
    ## Convert Inputs Outputs to Strings
    inputs = [f.finalpath for f in inputs]
    outputs = [f.finalpath for f in outputs]

    ostring = string
    m = r.search(ostring)
    ii = 0
    while m != None:
        ii += 1
        # perform lookup
        if m.group(1):
            # all out
            insert = " ".join(outputs)
        elif m.group(2):
            # all in
            insert = " ".join(inputs)
        elif m.group(3):
            # singout
            i = int(m.group(3))
            if i < 0 or i >= len(outputs):
                raise InputError("expand", "Error Resolving Output number "
                        "%i in\n%s" % (i, string))
            insert = outputs[i]
        elif m.group(4):
            # singin 
            i = int(m.group(4))
            if i < 0 or i >= len(inputs):
                raise InputError("expand", "Error Resolving input number "
                        "%i in\n%s" % (i, string))
            insert = inputs[i]
        elif m.group(5) and m.group(6):
            # sepvar
            k = str(m.group(6))
            if k not in defs:
                raise InputError("expand", "Error Resolving Variable "
                        "%s in\n%s" % (k, string))
            if type(defs[k]) == type([]):
                insert = m.group(5).join(defs[k])
            else:
                insert = m.group(5)+m.group(6)
        elif m.group(7):
            # var
            k = str(m.group(7))
            if k not in defs:
                raise InputError("expand", "Error Resolving Variable "
                        "%s in\n%s" % (k, string))
            if type(defs[k]) == type([]):
                insert = " ".join(defs[k])
            else:
                insert = defs[k]
        
        ostring = ostring[:m.start()] + insert + ostring[m.end():]
        m = r.search(ostring)
        if ii == 100:
            raise InputError("Circular Variable References Detected!")

    return string

###############################################################################
# Ent Class
###############################################################################
class Ent:
    """ Main Ent Class, all others are derived from this. This stores global 
    variables, all jobs, all files etc.

    Organization:
    Branch: This is a generic rule of how a particular set of inputs generates
    a particular set of outputs. 

    Ring: This is a concrete command to be run

    """
    error = 0
    files = dict()   # filename -> File
    variables = dict() # varname -> list of values
    rings = list()
    branches = list()

    def __init__(self, working):
        """ Ent Constructor """
        self.error = 0
        self.files = dict()
        self.variables = dict()
        self.rings = list()
        self.branches = list()

        # initialize special variables
        self.variables[".PWD"] = [working]

    def dumpJobs(self):
        pass

    def batch(self):
        """ Batch up all the jobs and generate a list of jobs that can be
        run simultaneously as a group"""

        fexist = set() # files that exist
        fronts = []

        queue = [rr for rr in self.rings]
        change = True 

        while len(queue) > 0 and change:
            # add any jobs that can be run to the current front
            print("Files created: %s " % fexist)
            front = []
            newexist = set()
            for rr in range(len(queue)):
                ready = True
                # check to see if all the inputs exist
                for ii in queue[rr].inputs:
                    if ii not in fexist:
                        print("%s doesn't exist yet" % ii)
                        ready = False
                        break

                # if its ready add to current front, add output
                # to list of done 
                if ready:
                    newexist.update(queue[rr].outputs)
                    front.append(queue[rr])
                    queue[rr] = None
                    change = True

            # done with current pass of queue, remove elements and 
            # add new exist files to fexist
            fexist.update(newexist)
            fronts.append(front)
            queue = [qq for qq in queue if qq != None];

        if len(queue) > 0:
            print("Error, jobs exist without a way to generate their inputs")
            return -1

        for ff in fronts:
            for rr in ff:
                print(rr.cmd)

    def run(self):
        """ Start the jobs """
        for rr in self.rings:
            rr.run()

    def setuptodate(self, filename):
        """ Reads a history file. Determines which files are 
        up to date, and which need to be updated.
        
        """ 
        
        # set all as out-of-date
        for fn, fclass in self.files.items():
            fclass.uptodate = False

        fhist = [()]
        
        # for each history file, check whether cache is out of date
        for fn in fhist:

            if fn.path in self.files:
                fclass = self.files[fn.path]
                cachef = join(self.cachedir, fclass.abspath)
                outf = fclass.abspath

                if fn.md5 == md5(cachef):
                    # cache file up to date
                    fclass.uptodate = True
                elif fn.md5 == md5(outf):
                    # cache not up to date, but out is
                    copy(source = outf, target = cachef)
                    fclass.uptodate = True
        
        # find all the generator-less inputs and make them uptodate by copying
        for fn, fclass in self.files.items():

            if fclass.genr == None and not fclass.uptodate:
                cachef = join(self.cachedir, fclass.abspath)
                outf = fclass.abspath
                copy(source = outf, target = cachef)

                fclass.uptodate = True

        # propagate uptodate status
        queue = [fclass for fclass in self.files.values() if not fclass.uptodate]
        while len(queue) > 0:
            fclass = queue.pop()
            
            # if not up to date, make all the children no up to date, and 
            # add to queue
            if not fclass.uptodate:
                # user is a ring that uses this as an input
                for user in fclass.users:

                    # child is an output from the given user ring
                    for child in user.outputs:
                        if fclass not in child.inputs:
                            return -1

                        # only enqueue if it hadn't been fixed yet
                        # prevents loops
                        if child.uptodate:
                            child.uptodate = False
                            queue.append(child)
        
        # alright everything should be up to date
        return 0

    def parseV1(self, filename):
        """Reads a file and makes modification to Ent class to incorporate
        the read files. This populates 

        self.files      - all inputs or outputs, dict of name->File
        self.rings      - jobs with specific inputs and outputs
        self.branches   - jobs prior to resolution
        self.variables  - global variables

        Variable names may be [a-zA-Z0-9_]*
        Variable values may be anything but white space, multiple values may
        be separated by white space

        """
        iomre = re.compile("\s*([^:]*?)\s*:(?!//)\s*(.*?)\s*")
        varre = re.compile("\s*([a-zA-Z0-9_.]*)\s*=\s*(.*?)\s*")
        cmdre = re.compile("\t\s*(.*?)\s*")
        commentre = re.compile("(.*?)#.*")

        with open(filename, "r") as f:
            lines = f.readlines()
        
        # so that any remaining branches get cleared
        lines.append("")
        lineno=0
        fullline = ""
        cbranch = None

        ## Clean Input
        # Merge Lines that end in \ and remove trailing white space:
        buff = []
        tmp = ""
        for line in lines:
            if line[-2:] == "\\\n":
                tmp += line[:-2]
            elif line[-3:] == "\\\r\n":
                tmp += line[:-3]
            else:
                buff.append(tmp+line.rstrip())
                tmp = ""
        lines = buff
        
        # Remove comments
        for ii in range(len(lines)):
            
            # remove comments
            match = commentre.search(lines[ii])
            if match:
                lines[ii] = match.group(1)

        for line in lines:
            if VERBOSE > 4: print("line %i:\n%s" % (lineno, line))

            # if there is a current branch we are working
            # the first try to append commands to it
            if cbranch:
                cmdmatch = cmdre.fullmatch(line)
                if cmdmatch:
                    # append the extra command to the branch
                    cbranch.cmds.append(cmdmatch.group(1))
                    continue
                else:
                    # done with current branch, remove current link
                    self.branches.append(cbranch)
                    if VERBOSE > 0: print("Adding branch: %s" % cbranch)
                    cbranch = None
            
            # if this isn't a command, try the other possibilities
            iomatch = iomre.fullmatch(line)
            varmatch = varre.fullmatch(line)
            if iomatch:
                # expand inputs/outputs
                inputs = re.split("\s+", iomatch.group(2))
                outputs = re.split("\s+", iomatch.group(1))
                inputs = [s for s in inputs if len(s) > 0]
                outputs = [s for s in outputs if len(s) > 0]

                # create a new branch
                cbranch = Branch(inputs, outputs)
                if VERBOSE > 3: print("New Branch: %s:%s" % (inputs, outputs))
            elif varmatch:
                # split variables
                name = varmatch.group(1)
                values = re.split("\s+", varmatch.group(2))
                if name in self.variables:
                    print("Error! Redefined variable: %s" % name)
                    return -1
                if VERBOSE > 3: print("Defining: %s = %s"%(name, str(values)))
                self.variables[name] = values
            else:
                continue

        if VERBOSE > 3: print("Done With Initial Pass!")

        # now go ahead and expand all the branches into rings
        for bb in self.branches:

            # get rings and files this generates
            rlist = bb.genRings(self.files, self.variables)

            if rlist == None:
                return -1

            # add rings to list of rings
            self.rings.extend(rlist)
            
        return 0

    def simulate(self):

        outqueue = []
        changed = False
        rqueue = self.rings
        while len(rqueue) > 0:
            curlen = len(rqueue) 
            
            done = []
            for i, ring in enumerate(rqueue):
                try:
                    cmds = ring.simulate(self.variables)
                    outqueue.extend(cmds)
                    done.append(i)
                except InputError:
                    pass

            # In the Real Runner we will also have to check weather there
            # are processes that are waiting
            if len(done) > 0:
                done.reverse()
                for i in done:
                    del(rqueue[i])
            else:
                print("Error The Following Rings of UnResolved Dependencies!")
                for rr in rqueue:
                    print(rr)
                raise InputError("Unresolved Dependencies")

        for cmd in outqueue:
            print(cmd)

###############################################################################
# File Class
###############################################################################
class File:
    """ 
    Keeps track of a particular files metdata. All jobs processes are wrapped
    in an md5 check, which returns success if it matches the previous value 
    """

    finalpath = ""  # final path to use for input/output
    force = ""      # force update of file even if file exists with the same md5
    genr = None     # pointer to the ring which generates the file
    users = []      # List of Downstream rings that need this file
    finished = False

    def __init__(self, path):
        """ Constructor for File class. 

        Parameters
        ----------
        path : string
            the input/output file path that may be on the local machine or on 
            any remote server
        """
        
        self.finalpath = path
        self.finished = False

        # Should be Updated By Ring
        self.genr = None 
        self.users = []
        
    # does whatever is necessary to produce this file
    def produce(self):
        if self.finished: 
            return True
        elif self.genr:
            return self.genr.run()
        else:
            raise InputError(self.finalpath, "No Branch Creates File")

    def __str__(self):
        if self.finished:
            return self.finalpath + " (done) "
        else:
            return self.finalpath + " (incomplete) "

###############################################################################
# Branch Class
###############################################################################
class Branch:
    """ 
    A branch is a job that has not been split up into rings (which are the
    actual jobs with resolved filenames). Thus each Branch may have any number
    of jobs associated with it.
    """

    cmds = list()
    inputs = list()
    outputs = list()

    def __init__(self, inputs, outputs):
        self.cmds = list()
        self.inputs = inputs
        self.outputs = outputs

    def genRings(self, gfiles, gvars):
        """ The "main" function of Branch is genRings. It produces a list of 
        rings (which are specific jobs with specific inputs and outputs)
        and updates files with any newly refernenced files. May need global
        gvars to resolve file names.
        
        Parameters
        ----------
        gfiles : (modified) dict, {filename: File} 
            global dictionary of files, will be updated with any new files found
        gvars : dict {varname: [value...] }
            global variables used to look up values
        
        """
        
        # produce all the rings from inputs/outputs
        rings = list()
        
        # store array of REAL output paths
        outputs = [self.outputs] 

        # store array of dictionaries that produced output paths, so that the
        # same variables to be reused for inputs
        valreal = [dict()] 

        # First Expand All Variables in outputs, for instance if there is a
        # variable in the output and the variable referrs to an array, that
        # produces mulitiple outputs
        while True:
            # outer list realization of set of outputs (list)
            prevout = outputs
            match = None
            oii = None
            ii = 0
            for outs in outputs:
                for out in outs:
                    
                    # find a variable
                    match = gvarre.fullmatch(out)
                    if match:
                        oii = ii
                        ii = len(outputs)
                        break;

                ii = ii+1
                if ii >= len(outputs):
                    break;

            # no matches in any of the outputs, break
            if not match:
                break

            pref = match.group(1)
            vname = match.group(2)
            suff = match.group(3)
            if vname not in gvars:
                raise InputError("genRings", "Error! Unknown global variable "
                        "reference: %s" % vv)

            subre = re.compile('\${\s*'+vname+'\s*}')
 
            # we already have a value for this, just use that
            if vname in valreal[oii]:
                vv = valreal[oii][vname]

                # perform replacement in all the gvars 
                for ojj in range(len(outputs[oii])):
                    outputs[oii][ojj] = subre.sub(vv, outputs[oii][ojj])

                # restart expansion process in case of references in the 
                # expanded value
                continue

            # no previous match, go ahead and expand
            values = gvars[vname]
            
            # save and remove matching realization
            outs = outputs[oii]
            del outputs[oii]
            varprev = valreal[oii]
            del valreal[oii]

            for vv in values:
                newouts = []
                newvar = copy.deepcopy(varprev)
                newvar[vname] = vv

                # perform replacement in all the gvars 
                for out in outs:
                    newouts.append(subre.sub(vv, out))
                
                outputs.append(newouts)
                valreal.append(newvar)

        # now that we have expanded the outputs, just need to expand input
        # and create a ring to store each realization of the expansion process
        for curouts, curvars in zip(outputs, valreal):
            curins = []

            # for each input, fill in variable values from outputs
            for inval in self.inputs:
                invals = [inval]
                
                # the expanded version (for instance if there are multi-value)
                # arguments
                final_invals = [] 
                while len(invals) > 0:
                    tmp = invals.pop()
                    match = gvarre.fullmatch(tmp)
                    if match:
                        pref = match.group(1)
                        name = match.group(2)
                        suff = match.group(3)

                        # resolve variable name
                        if name in curvars: 
                            # variable in the list of output vars, just sub in
                            invals.append(pref + curvars[name] + suff)
                        elif name in gvars:
                            # if it is a global variable, then we don't have a 
                            # value from output, if there are multiple values
                            # then it is a compound (multivalue) input
                            realvals = gvars[name]
                            if len(realvals) == 1:
                                tmp = pref + realvals[0] + suff
                                invals.append(tmp)
                            else:
                                # multiple values, insert in reverse order, 
                                # to make first value in list first to be 
                                # resolved in next iteration
                                tmp = [pref + vv + suff for vv in 
                                        reversed(realvals)]
                                invals.extend(tmp)
                        else:
                            print('Error, input "%s" references variable "%s"'\
                                    'which is a unknown!' % (inval, name))
                            return None
                        
                    else:
                        final_invals.append(tmp)
            
                # insert finalized invals into curins 
                curins.extend(final_invals)

            # find inputs and outputs in the global files database, and then
            # pass them in as a list to the new ring
            
            # change curins to list of Files, instead of strings
            print(curins)
            for ii, name in enumerate(curins):
                if name in gfiles:
                    curins[ii] = gfiles[name]
                else:
                    # since the file doesn't exist yet, create as placeholder
                    curins[ii] = File(name)
                    gfiles[name] = curins[ii]

            # find outputs (checking for double-producing is done in Ring, below)
            for ii, name in enumerate(curouts):
                if name in gfiles:
                    curouts[ii] = gfiles[name]
                else:
                    curouts[ii] = File(name)
                    gfiles[name] = curouts[ii]

            # append ring to list of rings
            oring = Ring(curins, curouts, self.cmds, self)
            if VERBOSE > 2: print("New Ring:%s"% str(oring))
            
            # append ring to list of rings
            rings.append(oring)

        # find external files referenced as inputs
        return rings 

    def __str__(self):
        tmp = "Branch"
        for cc in self.cmds:
            tmp = tmp + ("\tCommand: %s\n" % cc)
        tmp = tmp + ("\tInputs: %s\n" % self.inputs)
        tmp = tmp + ("\tOutputs: %s\n" % self.outputs)
        return tmp

###############################################################################
# Branch Class
###############################################################################
class Ring:
    """ A job with a concrete set of inputs and outputs """

    # inputs are nested so that outer values refer to 
    # values specified in the command [0] [1] : [0] [1]
    # and inner refer to any expanded values due to the 
    # referred values above actually including lists ie:
    # subj = 1 2 3
    # /ello : /hello/${subj} /world
    # inputs = [[/hello/1,/hello/2,/hello/3],[/world]]
    inputs = list() #list of input files   (File)
    outputs = list() #list of output files (File)
    cmds = []
    parent = None

    def __init__(self, inputs, outputs, cmds, parent = None):
        self.inputs = inputs
        self.outputs = outputs
        self.parent = parent
        self.cmds = cmds

        # make ourself the generator for the outputs
        for ff in self.outputs:
            if ff.genr:
                raise InputError(ff.finalpath, "Error! Generator already given")
            else:
                ff.genr = self

        # add ourself to the list of users of the inputs
        for igrp in self.inputs:
            ff.users.append(self)
        
    def run(self, globgen, trail):
        print("RUN")
 
    def simulate(self, globvars):
        # Check if all the inputs are ready
        ready = True
        for infile in self.inputs:
           if not infile.finished:
               ready = False
               break

        if ready:
            cmds = []
            for cmd in self.cmds:
                try:
                    cmd = " ".join(re.split("\s+", cmd))
                    cmd = expand(cmd, self.inputs, self.outputs, globvars)
                except InputError as e:
                    print("While Expanding Command %s" % cmd)
                    print(e.msg)
                    sys.exit(-1)
                cmds.append(cmd)
            
            for out in self.outputs:
                out.finished = True
            return cmds
        else:
            raise InputError("Ring: "+str(this)+" not yet ready")
            


    def __str__(self):
        out = "Ring\n"
        out = out + "\tParent:\n" 

        if self.parent:
            for cc in self.parent.cmds:
                out = out + ("\t\tCommand: %s\n" % cc)
            out = out + ("\t\tInputs: %s\n" % self.parent.inputs)
            out = out + ("\t\tOutputs: %s\n" % self.parent.outputs)

        out = out + "\tInputs: "
        count = 0
        for ii in self.inputs:
            out = out + "\n\t\t\t" + str(ii)
        out = out + "\n\tOutputs:"
        for ii in self.outputs:
            out = out + "\n\t\t\t" + str(ii)
        out = out + '\n'
        return out
