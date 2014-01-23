#!/usr/bin/env python
from optparse import OptionParser

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

import traceback
import subprocess
import os
import base64
import sys
import shelve

import yaml
try:
      from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
      from yaml import Loader, Dumper

from Crypto.Cipher import AES
from Crypto import Random

from multiprocessing import Process, JoinableQueue, Queue

TMP = '/tmp'
KEY_FILE = 'encrypt_key'
SHELVE = 'data'
NUMBER_OF_PROCESSES = 4 

pad_size = lambda s: AES.block_size - len(s) % AES.block_size
pad = lambda s, l: s + l * chr(l)


def get_backups():
  stream = file('backups.yaml', 'r')
  return yaml.load(stream, Loader=Loader)

def get_key():
  with open(KEY_FILE, 'r') as f:
    return f.read().strip()

def encrypt(f):
  iv = Random.new().read(AES.block_size)
  cipher = AES.new(get_key(), AES.MODE_CBC, iv)
  msg = iv + cipher.encrypt(pad(f, pad_size(f)))
  return msg

def get_drive():
  gauth = GoogleAuth()
  gauth.GetFlow()
  gauth.flow.params.update({'approval_prompt': 'force'})  #force accept button; get refresh token
  #gauth.LocalWebserverAuth() # Creates local webserver and auto handles authentication
  return GoogleDrive(gauth) # Create GoogleDrive instance with authenticated GoogleAuth instance

def upload_file(drive, f):
  print "Uploading %s..." % f
  attr = {} 
  if db.has_key(f) and len(db[f]) > 1:
    print "Adding revision to file id %s" % db[f][1]
    attr['id'] = db[f][1] 
  file = drive.CreateFile(attr)
  file.SetContentFile(f)
  file.Upload()
  print "%s uploaded." % f
  return file['id']

def confirm_backup(path):
    ok = 0
    while 1:
      print "Process %s ?" % path 
      c = sys.stdin.read(1)
      if c.lower() == 'n': 
        ok = 0
        break
      elif c.lower() == 'y': 
        ok = 1
        break

    return ok

def start_pool():
  for i in range(NUMBER_OF_PROCESSES):
    Process(target=worker, args=(task_queue, output_queue)).start()

def stop_pool():
  for i in range(NUMBER_OF_PROCESSES):
    task_queue.put('STOP')

def worker(input, output):
  for f, args in iter(input.get, 'STOP'):
    try:
      output.put(f(*args))
    finally:
      input.task_done()

def archive(path, file, encrypt=False, drive=None):
  print 'Archiving %s as %s' % (path, file)
  try:
    create_archive(path, file)
    hash = md5(file)
    if not options.force and db.has_key(file):
      if hash == db[file][0]:
        print "Archive %s %s = %s. Skipping..." % (file, hash, db[file][0])
        return 
      else:
        print "Archive %s %s != %s. Proceeding..." % (file, hash, db[file][0])

    u_file = file
    if encrypt:
      encrypt_archive(file)
      u_file += '.encrypted'
  
    id = None
    if drive:
      id = upload_file(drive, u_file)

    return (file, (hash, id))
  except Exception as e:
    traceback.print_exc()

def get_full_archive_name(archive):
    return os.path.join(TMP, archive) + '.tar.gz'

def create_archive(d, f):
  with open(f, 'w') as out_file:
    with open("NUL", 'w') as black_hole:
      tar = subprocess.Popen(('tar', '-c', d), stdout=subprocess.PIPE, stderr=black_hole)
    gzip = subprocess.Popen(('gzip', '-n'), stdin=tar.stdout, stdout=out_file)
    tar.stdout.close()
    gzip.communicate()

def encrypt_archive(f):
  print 'Encrypting %s...' % f
  with open(f, 'rb') as in_file:
    with open(f + '.encrypted', 'w') as out_file:
      out_file.write((encrypt(in_file.read())))

def md5(f):
  cmd = subprocess.Popen(('md5', f), stdout=subprocess.PIPE)
  hash = subprocess.check_output(('cut', '-d', ' ', '-f', '4'), stdin=cmd.stdout)
  cmd.stdout.close()
  print "%s has md5 %s" % (f, hash)
  return hash

def do(upload=True):
  drive = None
  for meta in get_backups()['backups']:
    d = meta['path']
    if options.confirm:
      if not confirm_backup(d):
        continue

    f = get_full_archive_name(meta['archive'])

    if meta.has_key('script'):
      s = meta['script']
      print 'Running script %s...' % s
      script = subprocess.Popen(s)
      if script.wait():
        print 'There was an error running %s. Skipping %s...' % (s, d)
        continue

    if upload and not drive:
      drive = get_drive() 
    task_queue.put((archive, (d, f, meta.has_key('encrypt'), drive)))

if __name__ == '__main__':
  db = shelve.open(SHELVE)
  task_queue = JoinableQueue()
  output_queue = Queue()

  parser = OptionParser()
  parser.add_option("-c", "--confirm", dest="confirm", default=False,
                        action="store_true", help="Confirm backups")
  parser.add_option("-f", "--force", dest="force", default=False,
                        action="store_true", help="Force uploads")
  (options, args) = parser.parse_args()
  
  try:
    start_pool()
    do()
    task_queue.join()
    stop_pool()

    while not output_queue.empty():
      result = output_queue.get()
      try:
        k, v = result
        db[k] = v
      except:
        pass
  finally:
    db.close()
