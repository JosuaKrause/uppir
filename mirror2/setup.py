#! /usr/bin/env python


from distutils.core import setup, Extension

import sys

print "This is not intended to be used for any serious purpose.  It is only"
print "constructed to build the C xordatastore.   There will be a serious"
print "version of this written later that covers more of upPIR..."


# Must have Python >= 2.5 and < 3.0.   If Python version == 2.5.X, then
# simplejson is required.
if sys.version_info[0] != 2 or sys.version_info[1] < 5:
  print "Requires Python >= 2.5 and < 3.0"
  sys.exit(1)

# We need a json library.   (We'll use the standard library json in Python 2.6 
# and greater...
if sys.version_info[1] == 5:
  try:
    import simplejson
  except ImportError:
    print "The package simplejson is required on Python 2.5.X"
    sys.exit(1)


fastsimpledatastore_c = Extension("fastsimplexordatastore_c",
    sources=["fastsimplexordatastore.c"])

setup(	name="upPIR",
    version="0.0-prealpha",
    ext_modules=[fastsimpledatastore_c],
    description="""An early version of upPIR with a simple C-based xordatastore.""",
    author="Justin Cappos",
    author_email="justinc@cs.washington.edu",
)


