#!/usr/bin/env python
from optparse import OptionParser

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

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

TMP = '/tmp'
KEY_FILE = 'encrypt_key'
SHELVE = 'data'

pad_size = lambda s: AES.block_size - len(s) % AES.block_size
pad = lambda s, l: s + l * chr(l)

parser = OptionParser()
parser.add_option("-c", "--confirm", dest="confirm", default=False,
                      action="store_true", help="Confirm backups")

(options, args) = parser.parse_args()

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
  attr = {} 
  if db.has_key(f):
    print "Adding revision to file id %s" % db[f]
    attr['id'] = db[f] 
  file = drive.CreateFile(attr)
  file.SetContentFile(f)
  file.Upload()
  db[f] = file['id']

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

def get_full_archive_name(archive):
    return os.path.join(TMP, archive) + '.tar.gz'

def create_archive(d, f):
  with open(f, 'w') as out_file:
    tar = subprocess.Popen(('tar', '-c', d), stdout=subprocess.PIPE)
    gzip = subprocess.Popen(('gzip'), stdin=tar.stdout, stdout=out_file)
    tar.stdout.close()
    gzip.communicate()

def encrypt_archive(f):
  print 'Encrypting %s...' % f
  with open(f, 'rb') as in_file:
    with open(f + '.encrypted', 'w') as out_file:
      out_file.write((encrypt(in_file.read())))

def archive(upload=True):
  drive = get_drive() 
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

    try:
      print 'Archiving %s as %s' % (d, f)
      create_archive(d, f)
    
      if meta.has_key('encrypt'):
        encrypt_archive(f)
        f += '.encrypted'
     
      if (upload):
        print "Uploading %s..." % f
        upload_file(drive, f)
    except Exception as e:
      print "Something bad happened:", str(e) 

db = shelve.open(SHELVE)
archive()
db.close()
