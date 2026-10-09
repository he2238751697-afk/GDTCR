#!/usr/bin/env python3
"""Cache DOI metadata and a dated, reproducible literature update search."""
import concurrent.futures
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path('paper/reference_metadata/revision_bmc')


def fetch(url, name):
    target = OUT / name
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'GDTCR-reference-audit/1.0'})
        with urllib.request.urlopen(request, timeout=40) as response:
            data = response.read()
            resolved = response.url
        target.write_bytes(data)
        return {'url': url, 'resolved_url': resolved, 'file': str(target),
                'sha256': hashlib.sha256(data).hexdigest(), 'status': 'ok'}
    except Exception as error:
        return {'url': url, 'status': 'unavailable', 'error': str(error)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    refs = json.load(open('paper/references_v2.json'))['references']
    jobs = [(r['key'], 'https://api.crossref.org/works/'+urllib.parse.quote(r['doi'],safe=''),
             r['key']+'_crossref.json') for r in refs]
    queries = {
        'gamma_delta_pairing': '(TITLE_ABS:"gamma delta" OR TITLE_ABS:"gamma-delta" OR TITLE_ABS:"γδ") AND (TITLE_ABS:pairing OR TITLE_ABS:paired OR TITLE_ABS:generation OR TITLE_ABS:prediction)',
        'tcr_language_benchmark': '(TITLE_ABS:"T cell receptor" OR TITLE_ABS:"T-cell receptor" OR TITLE_ABS:TCR) AND (TITLE_ABS:"language model" OR TITLE_ABS:benchmark OR TITLE_ABS:generative)',
        'sequence_split_benchmark': '(TITLE_ABS:protein OR TITLE_ABS:TCR) AND (TITLE_ABS:leakage OR TITLE_ABS:"sequence similarity") AND (TITLE_ABS:benchmark OR TITLE_ABS:prediction)',
    }
    for key, query in queries.items():
        query += ' AND FIRST_PDATE:[2025-01-01 TO 2026-10-06]'
        url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode(
            {'query': query, 'format': 'json', 'pageSize': 100, 'resultType': 'core', 'sort': 'FIRST_PDATE_D desc'})
        jobs.append((key,url,key+'_search.json'))
    jobs.append(('journal_guidelines','https://bmcbioinformatics.biomedcentral.com/submission-guidelines/preparing-your-manuscript/research-article','journal_guidelines.html'))
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        pending = {executor.submit(fetch,url,name): key for key,url,name in jobs}
        for future in concurrent.futures.as_completed(pending):
            key = pending[future]
            results[key] = future.result()
            print(key,results[key]['status'],flush=True)
    comparison = []
    for ref in refs:
        rec = results[ref['key']]
        if rec['status'] != 'ok':
            comparison.append({'key':ref['key'],'status':'metadata_unavailable'})
            continue
        m = json.loads(Path(rec['file']).read_text())['message']
        comparison.append({'key': ref['key'], 'doi': m['DOI'], 'title': m.get('title'),
            'journal': m.get('container-title'), 'volume': m.get('volume'), 'issue': m.get('issue'),
            'page': m.get('page'), 'article_number': m.get('article-number'),
            'published': m.get('published'), 'published_online': m.get('published-online'),
            'published_print': m.get('published-print'), 'type':m.get('type'),
            'original_reference':ref, 'authors':m.get('author')})
    report = {'search_date':'2026-10-06', 'scope':'Targeted literature update, not a systematic review',
              'queries':queries,'requests':results,'reference_comparison':comparison}
    (OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    main()
