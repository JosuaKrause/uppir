# on success, nothing is printed
import simplexorrequestor

# I'm keeping some of these datastructures tiny in order to make the output
# more readable if an error is discovered
mirrorinfolist = [{'name':'mirror1'}, {'name':'mirror2'}, {'name':'mirror3'}, {'name':'mirror4'}, {'name':'mirror5'}]
blocklist = [12,34]   
# this would usually be richer, but I only need these fields
manifestdict = {'blockcount':64, 'hashalgorithm':'noop', 
    'blockhashlist':['']*64}

rxgobj = simplexorrequestor.RandomXORRequestor(mirrorinfolist, blocklist, manifestdict, 2)

request1 = rxgobj.get_next_xorrequest()
request2 = rxgobj.get_next_xorrequest()

# success!
rxgobj.notify_success(request1,'a')
request3 = rxgobj.get_next_xorrequest()
# so request1 and request3 should be for the same mirror...
assert(request1[0] == request3[0])

# failure..
rxgobj.notify_failure(request2)
request4 = rxgobj.get_next_xorrequest()
assert(request2[0] != request4[0])
# so request2 and request4 should be for different mirrors...


# success!
rxgobj.notify_success(request3,'b')
# we're out of blocks to request from the first mirror...

rxgobj.notify_success(request4,chr(2))

# we're out of blocks to request from the first mirror...
request5 = rxgobj.get_next_xorrequest()
assert(request5[0] != request3[0])
assert(request5[0] == request4[0])
# we should have requested from the same mirror we tried before

rxgobj.notify_success(request5,chr(4))

# this should be ()
request6 = rxgobj.get_next_xorrequest()
assert(request6 == ())

# okay, now it's time to see if we get the right answer...  'a' ^ chr(2) == 'c'
answer1 = rxgobj.return_block(12)

# 'b' ^ chr(4) == 'f'
answer2 = rxgobj.return_block(34)

assert(answer1 == 'c')
assert(answer2 == 'f')





# Now let's try this where we chew through all of the mirrors to ensure we get
# the right exception
mirrorinfolist = [{'name':'mirror1'}, {'name':'mirror2'}, {'name':'mirror3'}]

rxgobj = simplexorrequestor.RandomXORRequestor(mirrorinfolist, blocklist, manifestdict, 2)

request1 = rxgobj.get_next_xorrequest()
request2 = rxgobj.get_next_xorrequest()

rxgobj.notify_failure(request1)
try:
  rxgobj.notify_failure(request2)
except simplexorrequestor.InsufficientMirrors:
  pass
else:
  print "Should be notified of insufficient mirrors!"

