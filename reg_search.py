#!/usr/bin/python
#! -*- encoding:utf-8 -*-

import urllib2
import re
import sys
import os


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
    
class TopList(object):
    
    def __init__(self):
        self.dict = {}
        self.url = 'http://music.baidu.com/top'
        self._load_top()
 
    def _load_top(self):
        text = urllib2.urlopen(self.url).read()
        head_reg = re.compile(r'<div class="head">(.+?)</div>',re.S)
        #<a href="/top/new" class="more">更多<span>&gt;&gt;</span></a>
        #<h2 class="title">新歌榜</h2>
        url_reg = re.compile(r'<a href="(.+?)".*?>.*?</a>')
        name_reg = re.compile(r'<h2 class=.+?>(.+?)</h2>')
        head_groups = re.findall(head_reg, text)
        
        for head in head_groups:
            url = search(url_reg, head)
            name = search(name_reg, head)
            self.dict.setdefault(name.group(1), url.group(1))
        
    def print_list(self):
        for key in self.dict:
            print 'Name: %s, URL: %s' % (key, dict[key])
            
              
            
if __name__ == '__main__':
    tl = TopList()
    tl.print_list
