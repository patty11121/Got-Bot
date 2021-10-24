import os
import git

direct = os.getcwd()
g = git.cmd.Git(direct)
g.pull
