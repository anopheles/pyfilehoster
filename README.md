pyfilehoster
=======

pyfilehoster provides a pythonic API to your favorite file hoster. Currently pyfilehoster supports retrieving data from hotfile and rapidshare.

## Sample usage using the RapidShare API
    credentials = ("username", "password")
    rsapi = RapidShareAPI(credentials)
    rsapi.upload_file(filepath)
    print rsapi.get_download_links()

Notes
--------
pyfilehoster is in parts compatible with google app engine. Thus pyfilehoster is written in python 2.5. Nonetheless it works with python 2.7.
Note that for obvious reasons uploading files won't work with GAE.

Currently pyfilehoster uses this perl script http://images.rapidshare.com/software/rsapiresume.pl in order to upload files.
You need to place it in the main directory of pyfilehoster in order to upload files to rapidshare. Also you must have perl installed.