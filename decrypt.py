#!/usr/bin/env python

import sys
from Crypto.Cipher import AES
from Crypto import Random

unpad = lambda s: s[:-ord(s[-1])]
KEY_FILE = 'encrypt_key'

def get_key():
  with open(KEY_FILE, 'r') as f:
    return f.read().strip()

def decrypt(enc ):
  iv = enc[:16]
  enc= enc[16:]
  cipher = AES.new(get_key(), AES.MODE_CBC, iv )
  return unpad(cipher.decrypt( enc))

if len(sys.argv) < 2:
  print "Must specify a file"
  exit(1)

with open(sys.argv[1], 'rb') as in_file:
  print decrypt(in_file.read())
