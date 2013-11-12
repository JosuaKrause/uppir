# let's print out some speed benchmarks about the datastore types...

# for timing...
import time

# for random bytes...
import random

# for ceil
import math

def random_bytes(size):
  
  # if it's huge, then repeat the same sequence every 64 biys
  if size % 64 == 0:
    return ("".join(chr(random.randrange(0, 256)) for i in xrange(64)))*(size/64)
  return "".join(chr(random.randrange(0, 256)) for i in xrange(size))


xordatastoremodules = ['fastsimplexordatastore', 'simplexordatastore']

blocksizestotest = [1024, 1024*4, 1024*16, 1024*64, 1024*256, 1024*1024, 1024*1024*4, 1024*1024*16]
numblockstotest = [16, 64, 256, 1024, 4*1024, 16*1024, 64*1024]


max_size_to_test = 64*1024*1024

ITERATIONS = 10

# let's go through the modules separately...
for modulename in xordatastoremodules:
  # import the module
  exec("import "+modulename)

  for blocksize in blocksizestotest:
    for numblocks in numblockstotest:

      # Okay, let's do this datastore...

      print modulename,"Blocksize:",blocksize,"blockcount:",numblocks,

      # if it's too big, skip it
      if blocksize*numblocks > max_size_to_test:
        print "Skipped!"
        continue


      # create the datastore
      thisxordatastore = eval(modulename+'.XORDatastore('+str(blocksize)+','+str(numblocks)+')')

      # I used to just plop the data in, but building huge strings took forever
      filledamount = 0
      while filledamount < blocksize*numblocks:
        amounttoadd = min(1024*64, blocksize*numblocks - filledamount)
        # let's fill it with random data...
        thisxordatastore.set_data(filledamount, random_bytes(amounttoadd))
        filledamount += amounttoadd


      bitstringlist = []
      # let's generate the random bitstrings
      for iteration in range(ITERATIONS):
        # need to generate a long enough string...
        bitstringlist.append(random_bytes(int(math.ceil(numblocks/8.0))))
        

      start = time.time()
      for bitstring in bitstringlist:
        thisxordatastore.produce_xor_from_bitstring(bitstring)
      print (time.time() - start)/ITERATIONS



