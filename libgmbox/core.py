#!/usr/bin/env python
# -*- coding: utf-8 -*-

__doc__ = '''gmbox核心库

这个库复制解析请求结果，并把结果转换为python对象。

基本对象：
Song: 歌曲
Songlist: 包含Song类的列表，子类是专辑、歌曲排行榜等。
Directory: 包含Songlist类（或子类）的列表，子类是搜索专辑，专辑排行榜等。

解析结果：
谷歌音乐的某些结果提供xml，通过它的flash播放器抓包分析所得。
某些功能没有xml，只好解析html，理论上解析速度会比xml慢。
'''

import logging
import urllib2
import urllib
import re
import sys
from threading import Thread
import Queue
from bs4 import BeautifulSoup
import json
from xml.dom import minidom

def get_logger(logger_name):
    ''' 获得一个logger '''
    format = '%(asctime)s %(levelname)s %(message)s'
    #level = logging.DEBUG
    level = logging.WARNING
    logging.basicConfig(format=format, level=level)
    logger = logging.getLogger(logger_name)
    return logger

logger = get_logger('baidumusic')

class GmObject(object):
    '''gmbox基本类

    定义共享工具类型的方法，子类实现具体方法。
    '''

    def __init__(self):
        self.gmattrs = {}

    def parse_dict(self, dict):
        '''解析dict键值添加实例属性'''

        for key, value in dict.iteritems():
            if not hasattr(self, key):
                self.gmattrs[key] = value
                setattr(self, key, value)
                
    def get_request(self, url):
        req = urllib2.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        return req

    @staticmethod
    def decode_html_text(text):
        '''转义html特殊符号'''

        html_escape_table = {
            "&nbsp;" : " ",
            "&quot;" : '"',
            "&ldquo;" : "“",
            "&rdquo;" : "”",
            "&mdash;" : "—",
            "&amp;" : "&",
            "&middot;" : "·"
        }
        for key, value in html_escape_table.iteritems():
            text = text.replace(key, value)
        numbers = re.findall('&#([^;]+);', text)
        for number in numbers:
            text = text.replace("&#%s;" % number, unichr(int(number)))
        return text
    
def handle_exception(func):
    def _wrapper(*args, **kwargs):
        try:
            func(args, kwargs)
        except urllib2.HTTPError, he:
            logger.error('Load tag failed!\n\tReason: %s' , he)
        except urllib2.URLError, ue:
            logger.error('Open url failed!\n\tReason: %s' , ue)
        return _wrapper

class PlayList(object):
    
    def __init__(self, name = None, file_path = None):
        self.list_name = name
        self.file_path = file_path
        pass
    
    def get_list_name_from_file(self, root):
        return root.childNodes[1][0].nodeValue
    
    def parse_xml(self):
        doc = minidom.parse(self.file_path)
        id_list = []
        
        root = doc.documentElement
        tracks = root.getElementsByTagName("track")
        for track in tracks:
            for child in track.childNodes:
                if child.nodeType == child.ELEMENT_NODE:
                    if child.nodeName == 'id':
                        id_list.append(child.childNodes[0].nodeValue)
        return id_list
        
    def create_node(self, dom, tag_name, data = None):
        tag = dom.createElement(tag_name)
        if data:
            text = dom.createTextNode(data)
            tag.appendChild(text)
        return tag
    
    def create_song_node(self, dom, song):
        song_node = dom.createElement('track')
        if hasattr(song, 'local_path'):
            location = self.create_node(dom, 'location', song.local_path)
        elif hasattr(song, 'listen_url'):
            location = self.create_node(dom, 'location', song.listen_url)
        else:
            location = self.create_node(dom, 'location', "")
        song_node.appendChild(location)
        artist = self.create_node(dom, 'artist', song.artist_name)
        song_node.appendChild(artist)
        song_title = self.create_node(dom, 'title', song.name)
        song_node.appendChild(song_title)
        song_id = self.create_node(dom, 'id', str(song.id))
        song_node.appendChild(song_id)
        album_name = self.create_node(dom, 'album', song.album_name)
        song_node.appendChild(album_name)
        
        return song_node
        
    def write_xml(self, songs):
        impl = minidom.getDOMImplementation()
        dom = impl.createDocument(None, 'playlist', None)
        root = dom.documentElement
        root.setAttribute('version', '1')
        
        title = self.create_node(dom, 'tilte', self.list_name)
        root.appendChild(title)
        
        track_list = self.create_node(dom, 'trackList')
        root.appendChild(track_list)
        
        for song in songs:
            song_node = self.create_song_node(dom, song)
            track_list.appendChild(song_node)
        
        with open(self.file_path, 'w') as fp:
            dom.writexml(fp, '  ', '  ', '\n', 'utf-8')    

class SongSet(GmObject):
    
    def __init__(self, sid_list = None):
        GmObject.__init__(self) 
        self.songs = []
        
        tmp_list = [ str(item) for item in sid_list]
        id_list = []
        for item in tmp_list:
            pos = item.find('#')
            if pos != -1:
                item = item[ : pos]
            id_list.append(item)
        self.query_url = 'http://play.baidu.com/data/music/songinfo?songIds=%s' % ','.join(id_list)
        self.query_req = urllib2.Request(self.query_url)
        self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        
        self.load_songs_info()
        
    def process_artist(self, name_list, id_list):
        artists = []
        for aname, aid in zip(name_list, id_list):
            artists.append([aid, aname])
        return artists
    
    def parse_info(self, info_dict):
        try:
            attr_dict = {}
            attr_dict.setdefault('name', info_dict['songName'])
            attr_dict.setdefault('id', info_dict['songId'])
            
            name_list = info_dict['artistName'].split(',')
            id_list = repr(info_dict['artistId']).split(',')
            artist_list = self.process_artist(name_list, id_list)
            attr_dict.setdefault('artist_list', artist_list)
            name_list = []
            for item in artist_list:
                name_list.append(item[1])
            artist_name = '&'.join(name_list)
            attr_dict.setdefault('artist_name', artist_name)
            
            attr_dict.setdefault('album_id', info_dict['albumId'])
            attr_dict.setdefault('album_name', info_dict['albumName'])
            attr_dict.setdefault('cover_url', info_dict['songPicBig'])
            
            return attr_dict
        except IndexError:
            return {}
        
    def load_songs_info(self):
        song_info = urllib2.urlopen(self.query_req).read()
        info_list = json.loads(song_info)['data']['songList']
        
        for item in info_list:
            attr_dict = self.parse_info(item)
            song = Song(attr_dict['id'])
            song.parse_dict(attr_dict)
            self.songs.append(song)

class Song(GmObject):
    '''歌曲类'''

    def __init__(self, sid = None):
        GmObject.__init__(self)
        if sid is not None:
            self.id = sid
                      
            self.link_url = 'http://play.baidu.com/data/music/songlink/?songIds=%s&hq=1&type=mp3' % self.id
            self.link_req = urllib2.Request(self.link_url)
            self.link_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.link_dict = {}
    
    def get_listen_url(self):
        rate_dict = self.link_dict['linkinfo']
        self.download_url = []
        if rate_dict is None:
            self.listen_url = self.link_dict['songLink']
            self.download_url = self.listen_url
            self.duration = self.link_dict['time']
        else:
            min_rate = 65535
            for key in rate_dict:
                rate = int(key)
                self.download_url.append((rate_dict[key]['songLink'], rate_dict[key]['size'], rate_dict[key]['time']))
                if rate < min_rate:
                    min_rate = rate
            min_rate = str(min_rate)
            self.listen_url = rate_dict[min_rate]['songLink']
            self.duration = rate_dict[min_rate]['time']
                 
    def load_song_link(self):
        if not hasattr(self, 'lyric_url') or not hasattr(self, 'link_dict'):
            song_link = urllib2.urlopen(self.link_req).read()
            link_dict = json.loads(song_link)
            self.link_dict = link_dict['data']['songList'][0]
            self.lyric_url = 'http://music.baidu.com%s' % self.link_dict['lrcLink']
            self.get_listen_url()

        
    def load_detail(self):
        '''读取详情数据
        详情数据是包含艺术家编号，封面地址等数据。
        调用这个函数会发出一个http请求，但只会发出一次，
        亦即数据已经读取了就不再发出http请求了。
        '''
        info_dict = self.load_song_info()
        self.parse_dict(info_dict)
            

class Songlist(GmObject):
    '''歌曲列表基本类，是歌曲(Song类）的集合

    定义共享解析的方法，分别是xml和html，部分内容可能没有xml提供。
    对于特别的情况，由子类覆盖方法实现。

    '''

    def __init__(self):
        GmObject.__init__(self)
        self.songs = []
        self.has_more = False

    def load_songs(self):
        '''读取歌曲列表里的歌曲，子类应覆盖这个方法

        调用self.load_songs后，self.songs会保存了本次请求的Song类的实例，
        例如：
        第一次调用self.load_songs后，self.songs只包含第一页的20首歌曲
        第二次调用self.load_songs后，self.songs只包含第二页的20首歌曲
        余下同理。

        所以请先从self.songs复制出Song实例后再调用self.load_songs，以免
        前面的结果被覆盖。
        可以检查self.has_more是否还有更多，亦即是否存在下一页。
        '''

        pass
    
    def load_more(self, page = 1, count = 20):
        
        pass
    
class FMList(GmObject):
    def __init__(self):
        GmObject.__init__(self)
        self.dict = {}
        self.req = self.get_request('http://fm.baidu.com')
        self.loaded = False
        
    def load_list(self):
        text = urllib2.urlopen(self.req).read()
        #rawChannelList = {"user_id":443884236,"user_name":"LogenSong","channel_list": [{"channel_id":"public_tuijian_summer","channel_name":"\u6e05\u51c9\u590f\u65e5","channel_order":10103,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":31},{"channel_id":"public_tuijian_rege","channel_name":"\u70ed\u6b4c","channel_order":10104,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":7},{"channel_id":"public_tuijian_ktv","channel_name":"KTV\u91d1\u66f2","channel_order":10105,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":4},{"channel_id":"public_tuijian_billboard","channel_name":"Billboard","channel_order":10106,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":17},{"channel_id":"public_tuijian_chengmingqu","channel_name":"\u6210\u540d\u66f2","channel_order":10107,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":8},{"channel_id":"public_tuijian_wangluo","channel_name":"\u7f51\u7edc\u7ea2\u6b4c","channel_order":10108,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":6},{"channel_id":"public_tuijian_yingshi","channel_name":"\u5f71\u89c6","channel_order":10109,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":33},{"channel_id":"public_tuijian_kaiche","channel_name":"\u5f00\u8f66","channel_order":10110,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":19},{"channel_id":"public_tuijian_suibiantingting","channel_name":"\u968f\u4fbf\u542c\u542c","channel_order":10113,"cate_id":"tuijian","cate":"\u63a8\u8350\u9891\u9053","cate_order":1,"pv_order":16},{"channel_id":"public_shiguang_jingdianlaoge","channel_name":"\u7ecf\u5178\u8001\u6b4c","channel_order":10201,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":3},{"channel_id":"public_shiguang_70hou","channel_name":"70\u540e","channel_order":10202,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":29},{"channel_id":"public_shiguang_80hou","channel_name":"80\u540e","channel_order":10203,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":10},{"channel_id":"public_shiguang_90hou","channel_name":"90\u540e","channel_order":10204,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":13},{"channel_id":"public_shiguang_xinge","channel_name":"\u706b\u7206\u65b0\u6b4c","channel_order":10205,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":26},{"channel_id":"public_shiguang_erge","channel_name":"\u513f\u6b4c","channel_order":10206,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":38},{"channel_id":"public_shiguang_lvxing","channel_name":"\u65c5\u884c","channel_order":10208,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":34},{"channel_id":"public_shiguang_yedian","channel_name":"\u591c\u5e97","channel_order":10209,"cate_id":"shiguang","cate":"\u65f6\u5149\u9891\u9053","cate_order":2,"pv_order":23},{"channel_id":"public_fengge_minyao","channel_name":"\u6c11\u8c23\u98ce\u666f","channel_order":10301,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":35},{"channel_id":"public_fengge_liuxing","channel_name":"\u6d41\u884c","channel_order":10302,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":11},{"channel_id":"public_fengge_dj","channel_name":"DJ\u821e\u66f2","channel_order":10303,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":20},{"channel_id":"public_fengge_qingyinyue","channel_name":"\u8f7b\u97f3\u4e50","channel_order":10304,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":15},{"channel_id":"public_fengge_xiaoqingxin","channel_name":"\u5c0f\u6e05\u65b0","channel_order":10305,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":25},{"channel_id":"public_fengge_zhongguofeng","channel_name":"\u4e2d\u56fd\u98ce","channel_order":10306,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":32},{"channel_id":"public_fengge_yaogun","channel_name":"\u6447\u6eda","channel_order":10308,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":36},{"channel_id":"public_fengge_dianyingyuansheng","channel_name":"\u7535\u5f71\u539f\u58f0","channel_order":10309,"cate_id":"fengge","cate":"\u98ce\u683c\u9891\u9053","cate_order":3,"pv_order":39},{"channel_id":"public_xinqing_qingsongjiari","channel_name":"\u8f7b\u677e\u5047\u65e5","channel_order":10401,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":22},{"channel_id":"public_xinqing_huankuai","channel_name":"\u5feb\u4e50\u65cb\u5f8b","channel_order":10402,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":12},{"channel_id":"public_xinqing_tianmi","channel_name":"\u751c\u871c\u611f\u53d7","channel_order":10403,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":28},{"channel_id":"public_xinqing_jimo","channel_name":"\u5bc2\u5bde\u7535\u6ce2","channel_order":10404,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":27},{"channel_id":"public_xinqing_qingge","channel_name":"\u5355\u8eab\u60c5\u6b4c","channel_order":10405,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":30},{"channel_id":"public_xinqing_shuhuan","channel_name":"\u8212\u7f13\u8282\u594f","channel_order":10406,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":14},{"channel_id":"public_xinqing_yonglanwuhou","channel_name":"\u6175\u61d2\u5348\u540e","channel_order":10407,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":21},{"channel_id":"public_xinqing_shanggan","channel_name":"\u4f24\u611f\u8c03\u9891","channel_order":10408,"cate_id":"xinqing","cate":"\u5fc3\u60c5\u9891\u9053","cate_order":4,"pv_order":18},{"channel_id":"public_yuzhong_huayu","channel_name":"\u534e\u8bed","channel_order":10501,"cate_id":"yuzhong","cate":"\u8bed\u79cd\u9891\u9053","cate_order":5,"pv_order":1},{"channel_id":"public_yuzhong_oumei","channel_name":"\u6b27\u7f8e","channel_order":10502,"cate_id":"yuzhong","cate":"\u8bed\u79cd\u9891\u9053","cate_order":5,"pv_order":5},{"channel_id":"public_yuzhong_riyu","channel_name":"\u65e5\u8bed","channel_order":10503,"cate_id":"yuzhong","cate":"\u8bed\u79cd\u9891\u9053","cate_order":5,"pv_order":40},{"channel_id":"public_yuzhong_hanyu","channel_name":"\u97e9\u8bed","channel_order":10504,"cate_id":"yuzhong","cate":"\u8bed\u79cd\u9891\u9053","cate_order":5,"pv_order":37},{"channel_id":"public_yuzhong_yueyu","channel_name":"\u7ca4\u8bed","channel_order":10505,"cate_id":"yuzhong","cate":"\u8bed\u79cd\u9891\u9053","cate_order":5,"pv_order":24}],"status":null}
        channel_reg = re.compile(r'rawChannelList = (.+?);', re.S)
        channel_match = channel_reg.search(text)
        if channel_match:
            info_dict = json.loads(channel_match.group(1))
            channel_list = info_dict['channel_list']
            for channel in channel_list:
                key = channel['cate_id']
                if key not in self.dict:
                    self.dict.setdefault(key, [channel['cate'], []])
                info_list = self.dict[key][1]
                info_list.append((channel['channel_id'], channel['channel_name']))

class TagList(GmObject):
    def __init__(self):
        GmObject.__init__(self)
        self.dict = {}
        self.req = self.get_request('http://music.baidu.com/tag')
        self.loaded = False
         
    def load_list(self):
        text = urllib2.urlopen(self.req).read()
        tag_reg = re.compile(r'<dl class="tag-mod" .*?>(.*?)</dl>', re.S)
        groups = re.findall(tag_reg, text)
             
        for item in groups:
            header_reg = re.compile(r'<dt><div>(.*?)</div></dt>')
            item_reg = re.compile(r'<span class="tag-list clearfix">.*?<a href="(.*?)" class=.*?>(.*?)</a>.*?</span>', re.S)
                 
            header_match = header_reg.search(item)
            if header_match:
                header_name = header_match.group(1)
            else:
                header_name = ""
            item_groups = re.findall(item_reg, item)
            tag_list = []
                 
            for tag in item_groups:
                tag_list.append((tag[1], tag[0]))
            self.dict.setdefault(GmObject.decode_html_text(header_name), tag_list)
        self.loaded = True
    
class Album(Songlist):
    '''专辑'''

    def __init__(self, album_id = None):
        Songlist.__init__(self)
        if album_id is not None:
            self.id = album_id
            url = "http://play.baidu.com/data/music/box/album?albumId=%s&type=album" % self.id
            self.req = self.get_request(url)
            self.load_detail()

    
    def load_detail(self):
        self.info_dict = json.loads(urllib2.urlopen(self.req).read())
        attr_dict = {}
        attr_dict.setdefault('cover_url', self.info_dict['data']['albumPicSmall'])
        attr_dict.setdefault('name', self.info_dict['data']['albumName'])
        attr_dict.setdefault('artists', [[0 ,self.info_dict['data']['artistName']]])
        
        self.parse_dict(attr_dict)
        
    def load_songs(self):        
        id_list = self.info_dict['data']['songIdList']
        song_set = SongSet(id_list)
        self.songs.extend(song_set.songs)
        
        return self.songs

class Search(Songlist):
    '''搜索'''
#http://music.baidu.com/data/user/getalbums?start=10&ting_uid=7994&order=time    artist - album
    def __init__(self, id = None):
        Songlist.__init__(self)
        if id is not None:
            self.id = id
            self.load_songs()
            
    def add_songs(self, content, count):
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        id_list = song_reg.findall(content)
        
        if len(id_list) == count:
            self.has_more = True
        else:
            self.has_more = False
        song_set = SongSet(id_list)
        songs = song_set.songs
        
        return songs

    def load_songs(self, start = 0, count = 20):
        template = "http://music.baidu.com/search/song?key=%s&start=%d&size=%d"
        url = template % (self.id, start, count)
        url = urllib.quote(url, ':?&/=')
        
        logger.info('读取搜索地址：%s', url)
        req = urllib2.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
        content = urllib2.urlopen(req).read()
        
        songs = self.add_songs(content, count)
        self.songs.extend(songs)
        return songs
    
    def load_more(self, page = 1, count = 20):
        start = page * count
        return self.load_songs(start, count)

# class Topiclisting(Songlist):
#     '''专题'''
# 
#     def __init__(self, id = None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/topiclisting?q=%s&cat=song&output=xml"
#         url = template % self.id
# 
#         logger.info('读取专题地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         xml = urlopener.read()
#         songs = self.parse_xml(xml)
#         self.songs.extend(songs)
#         return songs
            
class Chartlisting(Songlist):
    def __init__(self, top_id = None):
        Songlist.__init__(self)
        self.songs = []
        if top_id is not None:
            query_url = 'http://play.baidu.com/data/music/box/top?topId=%s' % top_id
            self.query_req = urllib2.Request(query_url)
            self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.load_songs()
        
    def add_songs(self, start, count):
        end = start + count
        if self.unloaded_count > count:
            self.has_more = True
            sub_list = self.id_list[start : end]
            song_set = SongSet(sub_list)
            self.unloaded_count -= count
        else:
            self.has_more = False
            song_set = SongSet(self.id_list)
            self.unloaded_count = 0
        
        return song_set.songs
    
    def load_songs(self, start = 0, count = 20):
        logger.debug('加载排行榜信息...')
        chart_dict = json.loads(urllib2.urlopen(self.query_req).read())
        self.id_list = chart_dict['data']['songIdList']
        
        self.unloaded_count = len(self.id_list)
        songs = self.add_songs(start, count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
        
        return self.songs
        
    def load_more(self, page = 1, count = 20):
        start = (page - 1) * count
        del self.songs[ : ]
        songs = self.add_songs(start, count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
                
        return self.songs
    
class Stylelisting(Songlist):
    def __init__(self, style_id = None):
        Songlist.__init__(self)
        self.style_id = style_id
        self.songs = []
        if self.style_id is not None:
            query_url = 'http://music.baidu.com/data/genres/getsongs?title=%s' % self.style_id
            self.query_req = urllib2.Request(query_url)
            self.query_req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64; rv:22.0) Gecko/20100101 Firefox/22.0')
            self.load_songs()
        
    def add_songs(self, data, count = 20):
        parse_content = urllib2.urlopen(self.query_req, data).read()
        info_dict = json.loads(parse_content)
        html = info_dict['data']['html']
        error_code = json.loads(parse_content)['errorCode']
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        if error_code != 22000:
            self.has_more = False
        id_list = song_reg.findall(html)
        if len(id_list) == count:
            self.has_more = True
        else:
            self.has_more = False
            
        song_set = SongSet(id_list)
        songs = song_set.songs
        
        return songs
    
    
    def load_songs(self, start = 0, count = 20):
        logger.debug('加载流派-%s信息...', self.style_id)
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        self.songs.extend(songs)
        
        return songs
        
        
    def load_more(self, page = 1, count = 20):
        start = page * count
        del self.songs[ : ]
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
                
        return self.songs
        
class Taglisting(Songlist):
     
    def __init__(self, tag_id):
        Songlist.__init__(self)
        self.next_songs = []
        if tag_id is not None:
            self.id = tag_id
            self.load_songs()
            
    def add_songs(self, content, count):
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        id_list = song_reg.findall(content)
        
        if len(id_list) >= count:
            self.has_more = True
        else:
            self.has_more = False
        song_set = SongSet(id_list)
        songs = song_set.songs[0 : count]
        self.next_songs = song_set.songs[count : ]
        
        return songs

    def retrieve_songs(self, start, count):
        template = "http://music.baidu.com/tag/%s?start=%d&size=%d"
        url = template % (self.id, start, count)
        url = urllib.quote(url, ':?&/=')
        req = self.get_request(url)
        content = urllib2.urlopen(req).read()
        
        songs = self.add_songs(content, count)
        return songs

    def load_songs(self, start = 0, count = 20):
        songs = self.retrieve_songs(start, count)
        self.songs.extend(songs)
        return songs
    
    def load_more(self, page = 1, count = 20):
        song_counts = len(self.next_songs)
        del self.songs[ : ]
        if song_counts < count:
            start = page * count
            self.songs.extend(self.next_songs[0 : ])
            songs = self.retrieve_songs(start, count)
            self.songs.extend(songs[0 : count - song_counts])
            del self.next_songs[ : ]
            self.next_songs = songs[count - song_counts : ]
        else:
            self.songs.extend(self.next_songs[0 : count])
            self.next_songs = self.next_songs[count : ]
        return self.songs
        

class ArtistSong(Songlist):
    '''艺术家'''
 
    def __init__(self, artist_id=None, artist_name = None):
        Songlist.__init__(self)
        if artist_id is not None:
            self.id = artist_id
            url = 'http://music.baidu.com/data/user/getsongs?ting_uid=%s&order=hot' % self.id
            self.query_req = self.get_request(url)
            self.name = artist_name
    
    def add_songs(self, data, count = 20):
        parse_content = urllib2.urlopen(self.query_req, data).read()
        info_dict = json.loads(parse_content)
        html = info_dict['data']['html']
        error_code = json.loads(parse_content)['errorCode']
        song_reg = re.compile(r'<a .*?href="/song/(.+?)".*?>')
        if error_code != 22000:
            self.has_more = False
        id_list = song_reg.findall(html)
        if len(id_list) == count:
            self.has_more = True
        else:
            self.has_more = False
            
        song_set = SongSet(id_list)
        songs = song_set.songs
        
        return songs
    
    
    def load_songs(self, start = 0, count = 20):
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        self.songs.extend(songs)
        
        return songs
        
        
    def load_more(self, page = 1, count = 20):
        start = page * count
        del self.songs[ : ]
        data = {'start' : start}
        songs = self.add_songs(urllib.urlencode(data), count)
        for song in songs:
            if hasattr(song, 'artist_list'):
                self.songs.append(song)
                
        return self.songs

# class Screener(Songlist):
#     '''挑歌
# 
#     args_dict 参数示例，字典类型
#     {
#         'timbre': '0.5', 
#         'date_l': '694195200000', 
#         'tempo': '0.5', 
#         'date_h': '788889600000', 
#         'pitch': '0.5', 
#         'artist_type': 'male'
#     }
#     '''
# 
#     def __init__(self, args_dict=None):
#         Songlist.__init__(self)
#         if args_dict is None:
#             self.args_dict = {}
#         else:
#             self.args_dict = args_dict
#         self.load_songs()
# 
#     def load_songs(self, start=0, number=20):
#         template = "http://www.google.cn/music/songscreen?start=%d&num=%d&client=&output=xml"
#         url = template % (start, number + 1)
# 
#         logger.info('读取挑歌地址：%s', url)
#         request_args = []
#         for key, value in self.args_dict.iteritems():
#             text = "&%s=%s" % (key, value)
#             request_args.append(text)
#         url = url + "".join(request_args)
#         urlopener = urllib2.urlopen(url)
#         xml = urlopener.read()
#         songs = self.parse_xml(xml)
#         if len(songs) == number + 1:
#             self.has_more = True
#             songs.pop()
#         else:
#             self.has_more = False
#         self.songs.extend(songs)
#         return songs

# class Similar(Songlist):
#     '''相似歌曲'''
# 
#     def __init__(self, id=None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/song?id=%s"
#         url = template % self.id
# 
#         logger.info('读取相似地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         html = urlopener.read()
#         songs = self.parse_html(html)
#         self.songs.extend(songs)
#         return songs
# 
# class Starrecc(Songlist):
#     '''大牌私房歌'''
# 
#     def __init__(self, id=None):
#         Songlist.__init__(self)
#         if id is not None:
#             self.id = id
#             self.load_songs()
# 
#     def load_songs(self):
#         template = "http://www.google.cn/music/playlist/playlist?id=sys:star_recc:%s&type=star_recommendation"
#         url = template % self.id
# 
#         logger.info('读取大牌私房歌地址：%s', url)
#         urlopener = urllib2.urlopen(url)
#         html = urlopener.read()
#         songs = self.parse_html(html)
#         self.songs.extend(songs)
#         return songs
# 
#     def parse_html(self, html):
#         ids = []
#         matches = re.findall('onclick="window.open([^"]+)"', html)
#         for match in matches:
#             match = re.search('download.html\?id=([^\\\]+)', urllib2.unquote(match)).group(1)
#             ids.append(match)
# 
#         names = []
#         artists = []
#         matches = re.findall('<td class="Title"><a .+?>《(.+?)》\n&nbsp;(.+?)</a></td>', html, re.DOTALL)
#         for match in matches:
#             name = GmObject.decode_html_text(match[0])
#             artist = GmObject.decode_html_text(match[1])
#             names.append(name)
#             artists.append(artist)
# 
#         songs = []
#         for i in range(len(ids)):
#             dict = {"id":ids[i], "name":names[i], "artist":artists[i]}
#             song = Song()
#             song.parse_dict(dict)
#             songs.append(song)
#         return songs

class Directory(GmObject):
    '''歌曲列表列表基本类，是歌曲列表(Songlist类）的集合，这里简称为“目录”
 
    类结构和Songlist相同，提供通用的解析方法，特殊情况由子类覆盖方法实现。
    '''
 
    def __init__(self):
        self.songlists = []
        self.has_more = False
 
    def load_songlists(self, start = 0, count = 10):
        '''读取目录里的歌曲列表，子类应覆盖这个方法
 
        原理类似Songlist类的load_songs方法，请参考该类注释，只不过Songlist类
        实用self.songs而这个类使用self.songlists。
        '''
 
        pass
 
class DirSearch(Directory):
    '''专辑搜索'''

    def __init__(self, dir_name):
        Directory.__init__(self)
        self.id = dir_name
        self.load_songlists()

    def load_songlists(self, start = 0, count = 10):
        url = 'http://music.baidu.com/search/album?key=%s&start=%d&size=%d' % (self.id, start, count)
        req = self.get_request(url)
        logger.info('读取专辑搜索地址: %s', url)
        
        content = urllib2.urlopen(req).read()
        album_reg = re.compile(r'<a .*?href="/album/(.+?)" title="\S*".*?>')
        album_list = album_reg.findall(content)
        album_list = list(set(album_list))
        if len(album_list) == count:
            self.has_more = True
        else:
            self.has_more = False
        songlists = []
        for album_id in album_list:
            album = Album(album_id)
            songlists.append(album)
        
        self.songlists.extend(songlists)
        return songlists
    
    def load_more(self, page = 1, count = 10):
        start = page * count
        return self.load_songlists(start, count)


class DirArtist(Directory):
    '''艺术家搜索'''

    def __init__(self, artist_name):
        Directory.__init__(self)
        self.name = artist_name
        self.load_songlists()
        
    def load_artist_id(self):
        self.url = 'http://music.baidu.com/search/artist?key=%s' % self.name
        req = self.get_request(self.url)
        content = urllib2.urlopen(req).read()
        
        redirect_reg = re.compile(r'<div class="name">\s*<a href="(.+?)">.*?</div>', re.S)
        redirect_match = redirect_reg.search(content)
        if redirect_match:
            artist_url = 'http://music.baidu.com%s' % redirect_match.group(1)
        else:       #TODO: add error handler
            artist_url = 'http://music.baidu.com'
        req = self.get_request(artist_url)
        content = urllib2.urlopen(req).read()
        id_reg = re.compile(r'<div .*?ting_uid="(\d+?)">', re.S)
        id_match = id_reg.search(content)
        if id_match:
            self.artist_id = id_match.group(1)

    def load_songlists(self, start=0, number=20):
        if not hasattr(self, 'artist_id'):
            self.load_artist_id()

        logger.info('读取艺术家搜索地址：%s', self.url)
        songlists = []
        artist = ArtistSong(self.artist_id, self.name)
        songlists.append(artist)
        
        self.songlists.extend(songlists)
        return songlists
    
    def load_more(self, page = 1, count = 20):
        start = page * count
        return self.load_songlists(start, count)

class DirArtistAlbum(Directory):
    ''' 艺术家专辑 '''

    def __init__(self, id):
        Directory.__init__(self)
        self.id = id
        self.load_songlists()

    def parse_html(self, html):

        ids = []
        matches = re.findall('<!--freemusic/album/result/([^-]+)-->', html)
        for match in matches:
            ids.append(match)

        names = []
        matches = re.findall('《(.+)》</a>&nbsp;-&nbsp;', html)
        for match in matches:
            match = match.replace("<b>", "")
            match = match.replace("</b>", "")
            match = GmObject.decode_html_text(match)
            names.append(match)

        artists = []
        matches = re.findall('<td class="Tracks" colspan="10" align="left">(.+?)</td>', html)
        for match in matches:
            match = match.replace("<b>", "")
            match = match.replace("</b>", "")
            match = match.split()[0]
            match = GmObject.decode_html_text(match)
            artists.append(match)

        thumbnails = []
        matches = re.findall('<img [^/]+ class="thumb-img" [^/]+ src="([^"]+)"', html)
        for match in matches:
            thumbnails.append(match)
        #上面的的正则表达式同样匹配艺术家头像，位置在第一，所以要去掉。
        thumbnails = thumbnails[1:]

        songlists = []
        for i in range(len(ids)):
            dict = {"id":ids[i], "name":names[i], "artist":artists[i], "thumbnailLink":thumbnails[i]}
            album = Album()
            album.parse_dict(dict)
            songlists.append(album)
        return songlists

    def load_songlists(self):
        template = "http://www.google.cn/music/artist?id=%s"
        url = template % self.id

        logger.info('读取艺术家专辑地址：%s', url)
        urlopener = urllib2.urlopen(url)
        html = urlopener.read()
        songlists = self.parse_html(html)
        self.songlists.extend(songlists)
        return songlists
    
class Channel(Songlist):
    def __init__(self):
        Songlist.__init__(self)
    
#class Songs(object):
    #http://music.baidu.com/data/music/songlist/list?start=0&size=8&tagname=%E5%8A%B1%E5%BF%97
    #http://fm.baidu.com/dev/api/?tn=playlist&id=public_fengge_liuxing&special=flash&format=json        fm
    #http://fm.baidu.com/dev/api/?action=userop&tn=userop&data=1|4|1|279134|public_tuijian_ktv      update song