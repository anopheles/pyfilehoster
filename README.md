pyfilehoster
=======

pyfilehoster is a pythonic API to your favorite file hoster. Currently pyfilehoster supports retrieving data from hotfile and rapidshare.

## Sample usage using the RapidShare API
    credentials = ("username", "password")
    rsapi = RapidShareAPI(credentials)
    rsapi.upload_file(filepath)
    print rsapi.get_download_links()
