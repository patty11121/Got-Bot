import os
import git

direct = os.getcwd()
print(direct)
g = git.cmd.Git(direct)
g.pull
