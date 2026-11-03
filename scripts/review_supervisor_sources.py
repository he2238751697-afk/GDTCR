#!/usr/bin/env python3
"""Retrieve public journal instructions and reference metadata for the review draft."""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'paper/supervisor_review/source_checks'
DATE='2026-11-03'


class PlainText(HTMLParser):
    def __init__(self):super().__init__();self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'GDTCR-manuscript-reference-check/1.0','Accept':'application/json,text/html'})
    with urllib.request.urlopen(request,timeout=35) as response:return response.read()


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')


def journal(item):
    key,url=item
    try:
        raw=get(url);parser=PlainText();parser.feed(raw.decode('utf-8','replace'))
        text=re.sub(r'\s+',' ',' '.join(parser.parts))
        phrases=['The Abstract should','Original Papers','Research Article','Research article','Review Article','word limit','words','Impact Factor','Impact factor','impact factor','Journal Citation','benchmark','Benchmark','substantial advance','scientifically valid','data availability','Data availability']
        excerpts=[]
        for phrase in phrases:
            for m in list(re.finditer(re.escape(phrase),text))[:4]:
                excerpts.append({'keyword':phrase,'text':text[max(0,m.start()-100):m.start()+950]})
        result={'url':url,'checked':DATE,'retrieved':True,'page_sha256':hashlib.sha256(raw).hexdigest(),'excerpts':excerpts}
    except Exception as e:result={'url':url,'checked':DATE,'retrieved':False,'error':str(e)}
    save(key+'.json',result);return key,result


def reference(record):
    url='https://api.crossref.org/works/'+urllib.parse.quote(record['doi'],safe='')
    try:
        message=json.loads(get(url))['message']
        selected={k:message.get(k) for k in ('DOI','title','container-title','type','volume','issue','page','article-number','published','published-print','published-online','relation')}
        selected['authors']=[{k:a.get(k) for k in ('given','family')} for a in message.get('author',[])]
        result={'key':record['key'],'url':url,'checked':DATE,'retrieved':True,'metadata':selected,
                'previous_metadata_file':record['verification_source'],'previous_metadata_sha256':record['verification_sha256']}
    except Exception as e:result={'key':record['key'],'url':url,'checked':DATE,'retrieved':False,'error':str(e)}
    save('reference_'+record['key']+'.json',result);return record['key'],result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pages=[('bmc_guidelines','https://link.springer.com/journal/12859/submission-guidelines/research-article'),
           ('bmc_scope','https://link.springer.com/journal/12859/aims-and-scope'),
           ('bmc_metrics','https://link.springer.com/journal/12859'),
           ('bib_guidelines','https://academic.oup.com/bib/pages/General_Instructions'),
           ('bib_metrics','https://academic.oup.com/bib/pages/About'),
           ('bioinformatics_guidelines','https://academic.oup.com/bioinformatics/pages/General_Instructions'),
           ('bioinformatics_metrics','https://academic.oup.com/bioinformatics/pages/About')]
    refs=json.loads((ROOT/'paper/references_bmc.json').read_text())['references']
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(journal,p) for p in pages]+[pool.submit(reference,r) for r in refs]
        results=dict(f.result() for f in concurrent.futures.as_completed(futures))
    queries=[
        '("gamma delta" OR "gamma-delta" OR "paired-chain" OR "paired chain") AND (TCR OR "T cell receptor") AND FIRST_PDATE:[2026-10-07 TO 2026-11-03]',
        '("T cell receptor" OR TCR) AND (pairing OR "partner recovery" OR "sequence generation") AND FIRST_PDATE:[2026-10-07 TO 2026-11-03]']
    searches=[]
    for query in queries:
        url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':query,'format':'json','pageSize':100,'resultType':'core'})
        try:
            response=json.loads(get(url));items=response.get('resultList',{}).get('result',[])
            result={'query':query,'url':url,'checked':DATE,'retrieved':True,'hit_count':response.get('hitCount'),'results':[{k:x.get(k) for k in ('id','source','doi','title','authorString','firstPublicationDate','pubYear','abstractText','pubTypeList')} for x in items]}
        except Exception as e:result={'query':query,'url':url,'checked':DATE,'retrieved':False,'error':str(e)}
        searches.append(result)
    save('targeted_literature_search.json',{'date':DATE,'database':'Europe PMC','searches':searches,'scope':'Targeted update since the prior 6 October check; not a systematic review.'})
    save('retrieval_status.json',{'checked':DATE,'sources':{k:{'retrieved':v['retrieved'],'url':v['url']} for k,v in results.items()}})
    print(json.dumps({'sources_retrieved':sum(v['retrieved'] for v in results.values()),'sources':len(results),'search_hits':[s.get('hit_count') for s in searches],'failures':[k for k,v in results.items() if not v['retrieved']]}))


if __name__=='__main__':main()
