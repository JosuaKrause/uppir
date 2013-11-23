cd vendor
rm manifest.dat vendor.log
python uppir_create_manifest.py ../filestoshare/ 1024 127.0.0.1
python uppir_vendor.py --foreground &
sleep 1
cd ../mirror1
rm manifest.dat mirror.log
python uppir_mirror.py --ip=127.0.0.1 --port 62001 --foreground --mirrorroot=../filestoshare/ --httpport=61002 --retrievemanifestfrom=127.0.0.1 &
cd ../mirror2
rm manifest.dat mirror.log
python uppir_mirror.py --ip=127.0.0.1 --port 62002 --foreground --mirrorroot=../filestoshare/ --httpport=61002 --retrievemanifestfrom=127.0.0.1 &
cd ../mirror3
rm manifest.dat mirror.log
python uppir_mirror.py --ip=127.0.0.1 --port 62003 --foreground --mirrorroot=../filestoshare/ --httpport=61002 --retrievemanifestfrom=127.0.0.1 &
cd ..
