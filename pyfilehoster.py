# -*- coding: utf-8 -*-

import subprocess
import shlex
import urllib
import urllib2
import os
import re

from functools import partial
from urlparse import  urlparse, urlunparse

try:
    from ftplib import FTP
except ImportError:
    pass


# Defines the block size of the chunks being uploaded
UPLOAD_BLOCKSIZE = 8192 * 4

class HosterAPI(object):

    def get_download_links(self):
        """
            returns a dictionary with file ids as keys
            each value is saved as a dictionary with at least the keys filename and url
        """
        raise NotImplementedError

    def delete_remote_file(self):
        """
            returns True if successful, False otherwise
        """
        raise NotImplementedError

    def delete_contents_of_folder(self, folderid):
        raise NotImplementedError

    def get_folder_hierarchy(self, folderid=None):
        """
            returns a dictionary containing the folder hierarchy
        """
        raise NotImplementedError

    def upload_file(self, filepath):
        raise NotImplementedError

    def set_direct_download(self, force=True, *fileids):
        raise NotImplementedError

class Counter():
    def __init__(self):
        self.value = 1

    def increment(self):
        self.value += 1

class HosterAPIError(Exception): pass

def upload_feedback(hoster, filepath, counter, uploaded_data):
    file_size = os.path.getsize(filepath)
    counter.increment()
    upload_progress = (counter.value * UPLOAD_BLOCKSIZE) / float(file_size)
    print 'Uploading to: %s %.2f%%' % (hoster, upload_progress * 100)


class Directory(object):

    def __init__(self, id, name, parentid):
        self.id = id
        self.name = name
        self.parentid = parentid
        self.children = {}
        self.files = {}

    def __repr__(self):
        return "Directory(%s, %s, %s, %s)" % (self.id, self.name, self.parentid, self.children)

class RapidShareAPI(HosterAPI):
    """
        implements http://images.rapidshare.com/apidoc.txt
    """
    def __init__(self, credentials=None, secure=False):
        self.scheme = "http%s" % ("s" if secure else "")
        #scheme, netloc, url, params, query, fragment = data
        self.base_url = [self.scheme, "api.rapidshare.com", "cgi-bin/rsapi.cgi", "", "", ""]
        try:
            self.username, self.password = credentials
            query = urllib.urlencode({"login": self.username,
                                      "password": self.password})
            self.base_url[4] = query
        except TypeError:
            pass

    def _catch_error(self, lines, url):
        for index, line in enumerate(lines):
            if index == 0 and "ERROR: " in line:
                raise HosterAPIError, line[7:]+" URL: %s" % url

    def get_folder_hierarchy(self, folderid=None):
        flat = []
        folder_api_url = self.base_url[:]
        query = urllib.urlencode({"sub": "listrealfolders"})
        folder_api_url[4] += "&"+query
        url = urlunparse(folder_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            current_folderid, parentid, foldername = line.split(",")
            if parentid == "999":
                pass # directory has been deleted
            else:
                flat.append(Directory(current_folderid, foldername.replace("\n", ""), parentid))

        id2directory = dict((d.id, d) for d in flat)
        id2directory["0"] = root = Directory("0","root", "0")
        for directory in flat:
            try:
                id2directory[directory.parentid].children[directory.id] = directory
            except KeyError:
                pass # This exception eliminates all children who don't have parents

        if folderid is not None:
            return id2directory[folderid].children
        return root.children

    def set_direct_download(self, force=True, *fileids):
        direct_download_api_url = self.base_url[:]
        query = urllib.urlencode({"sub": "trafficsharetype",
                                  "files": ",".join(fileids),
                                  "trafficsharetype": 1 if force else 0})
        direct_download_api_url[4] += "&"+query
        url = urlunparse(direct_download_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            if "OK" in line:
                return True
        return False

    def get_download_links(self, folderid=None, fields=""):
        download_links = dict()
        download_api_url = self.base_url[:]
        fields = (set(fields.split(",")) | set(["filename"])) - set([""])
        if len(fields) > 1:
            supported_fields = set("downloads,lastdownload,filename,size,killcode,serverid,type,x,y,realfolder,bodtype,killdeadline,licids,uploadtime".split(","))
            for field in fields:
                if field not in supported_fields:
                    raise HosterAPIError, "field: %s not supported" % field
        query = urllib.urlencode({"sub": "listfiles",
                                  "fields": ",".join(fields)})
        download_api_url[4] += "&"+query
        if folderid is not None:
            query = urllib.urlencode({"realfolder": folderid})
            download_api_url[4] += "&"+query
        url = urlunparse(download_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            try:
                rows = line.split(",")
                fileid = rows[0]
                properties = dict(zip(fields, rows[1:]))
                properties["filename"] = properties["filename"].replace("\n", "")
                download_url = [self.scheme, "rapidshare.com", "files/%s/%s" % (fileid, properties["filename"]), "", "", ""]
                properties["url"] = urlunparse(download_url)
                download_links[fileid] = properties
            except (ValueError, KeyError):
                pass
        return download_links

    def upload_file(self, filepath, folderid=None, overwrite=True):
        if overwrite:
            for fileid, properties in self.get_download_links(folderid=folderid).iteritems():
                if properties["filename"] == os.path.basename(filepath):
                    self.delete_remote_file(fileid)
                    
        perl_script_path = os.path.join(os.path.dirname(__file__), "rsapiresume.pl")
        args = shlex.split('perl "%s" "%s" %s %s 1 2' % (perl_script_path, filepath, self.username, self.password))
        output = subprocess.Popen(args, shell=True, stdout=subprocess.PIPE).communicate()[0]
        if folderid is not None:
            download_link = urlparse(re.search(r'File1.1=([\w].*)', output).group(1))
            fileid = download_link.path.split('/')[2]
            self.move_file_to_folder(folderid, fileid)

    def move_file_to_folder(self, folderid, *fileids):
        move_file_api_call = self.base_url[:]
        query = urllib.urlencode({"sub": "movefilestorealfolder",
                                  "files": ",".join(fileids),
                                  "folder": folderid})
        move_file_api_call[4] += "&"+query
        url = urlunparse(move_file_api_call)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            if "OK" in line:
                return True
        return False

    def delete_remote_file(self, *fileids):
        delete_api_url = self.base_url[:]
        query = urllib.urlencode({"sub": "deletefiles",
                                  "files": ",".join(fileids)})
        delete_api_url[4] += "&"+query
        url = urlunparse(delete_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            if "OK" in line:
                return True
        return False

class HotFileAPI(HosterAPI):
    """
        implements http://api.hotfile.com/
    """

    def __init__(self, credentials=None, secure=False):
        self.scheme = "http%s" % ("s" if secure else "")
        #scheme, netloc, url, params, query, fragment = data
        self.base_url = [self.scheme, "api.hotfile.com", "/", "", "", ""]
        try:
            self.username, self.password = credentials
            query = urllib.urlencode({"username": self.username,
                                      "password": self.password})
            self.base_url[4] = query
        except ValueError:
            pass

    def _catch_error(self, lines, url):
        for index, line in enumerate(lines):
            if index == 0 and line[0] == ".":
                raise HosterAPIError, line[1:]++" url: %s" % url

    def get_download_links(self, folderid, hashid):
        download_links = dict()
        download_api_url = self.base_url[:]
        query = urllib.urlencode({"action": "getdownloadlinksfrompublicdirectory",
                                  "folder": folderid,
                                  "hash": hashid})
        download_api_url[4] += "&"+query
        url = urlunparse(download_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            try:
                filename, download_link = line.split("|")
                fileid =  urlparse(download_link).path.split("/")[2]
                download_links[fileid] = {"filename" : filename,
                                          "url" : download_link.replace("\n","")}
            except ValueError:
                pass
        return download_links

    def set_direct_download(self, fileid, force=True):
        direct_download_api_url = self.base_url[:]
        query = urllib.urlencode({"action": "hotlinkfile",
                                  "fileid": fileid,
                                  "hotlink": 1 if force else 0})
        direct_download_api_url[4] += "&"+query
        url = urlunparse(direct_download_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            if "OK" in line:
                return True
        return False

    def delete_remote_file(self, folderid, fileid):
        delete_api_url = self.base_url[:]
        query = urllib.urlencode({"action": "deletefile",
                                  "folderid": folderid,
                                  "fileid": fileid})
        delete_api_url[4] += "&"+query
        url = urlunparse(delete_api_url)
        lines = urllib2.urlopen(url).readlines()
        self._catch_error(lines, url)
        for line in lines:
            if "OK" in line:
                return True
        return False

    def delete_contents_of_folder(self, folderid, hashid):
        for element in self.get_download_links(folderid, hashid).values():
            filename, download_url = element
            self.delete_remote_file(folderid, filename)

            
    def upload_file(self, filepath, folderid=None, hashid=None, path="", overwrite=True):
        if overwrite:
            for fileid, properties in self.get_download_links(folderid, hashid).iteritems():
                if properties["filename"] == os.path.basename(filepath):
                    self.delete_remote_file(folderid, fileid)

        ftp = FTP("ftp.hotfile.com")
        ftp.login(user=self.username, passwd=self.password)
        ftp.storbinary("STOR %s/" % path + os.path.basename(filepath), open(filepath, "rb"),
                       blocksize=UPLOAD_BLOCKSIZE,
                       callback=partial(upload_feedback, "Hotfile", filepath, Counter()))
        ftp.quit()