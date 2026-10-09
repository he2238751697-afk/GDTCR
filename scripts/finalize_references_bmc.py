#!/usr/bin/env python3
"""Combine verified Crossref, Europe PMC and publisher reference records."""
import hashlib,json,re
from pathlib import Path

def main():
    folder=Path('paper/reference_metadata/revision_bmc')
    original=json.load(open('paper/references_v2.json'))['references'];rows=[]
    for ref in original:
        key=ref['key'];p=folder/(key+'_crossref.json')
        if p.exists():
            m=json.load(open(p))['message'];assert m['DOI'].lower()==ref['doi'].lower()
            item={**ref,'issue':m.get('issue',ref.get('issue')),'verification_source':str(p)}
        else:
            p=folder/(ref['doi'].split('/')[-1]+'_epmc.json');r=json.load(open(p))['resultList']['result'][0]
            assert r['doi'].lower()==ref['doi'].lower();j=r['journalInfo']
            item={**ref,'volume':j.get('volume'),'issue':j.get('issue'),'pages_or_article':r.get('pageInfo'),
                  'verification_source':str(p)}
        if key=='tcrbert':
            p=folder/'tcrbert_publisher.json';r=json.load(open(p))['collection'][0]
            item.update(title=r['title'],verification_source=str(p),
                        metadata_note='Crossref and Europe PMC add a spurious x in antigen-xbinding. Publisher API confirms antigen-binding; manuscript retains publisher title.')
        item['verified_date']='2026-10-06';item['verification_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();rows.append(item)
    for key,doi in [('dtcr','10.1093/bib/bbag438'),('germline_shortcut','10.64898/2026.07.21.739963')]:
        p=folder/(key+'_crossref.json');m=json.load(open(p))['message'];assert m['DOI'].lower()==doi
        rows.append({'key':key,'doi':doi,'title':re.sub('<[^>]+>','',m['title'][0]),'authors':m.get('author'),
                     'volume':m.get('volume'),'issue':m.get('issue'),'pages_or_article':m.get('page') or m.get('article-number'),
                     'year':2026,'type':'preprint' if key=='germline_shortcut' else 'journal-article',
                     'verification_source':str(p),'verified_date':'2026-10-06','verification_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    Path('paper/references_bmc.json').write_text(json.dumps({'verified_date':'2026-10-06','references':rows},ensure_ascii=False,indent=2)+'\n')
    lines=['# BMC revision reference audit','','Checked on 6 October 2026. All 16 cited DOIs were verified against Crossref, Europe PMC or publisher metadata. Volume/issue/article identifiers were checked; online-first dates are distinguished from issue years.','','| Citation | DOI | Volume(issue), pages/article | Record |','| --- | --- | --- | --- |']
    for r in rows:
        lines.append(f"| {r['key']} | {r['doi']} | {r.get('volume') or 'Preprint'} ({r.get('issue') or 'not assigned'}), {r.get('pages_or_article') or 'DOI identifies record'} | {r['verification_source']} |")
    lines+=['','Crossref rate-limited three requests (UcTCRdb, OTS and Landry); exact-DOI Europe PMC records supplied the verified fields. TCR-BERT has a database title typo; the publisher API confirms the manuscript wording. No DOI or result was invented.','','The dated Europe PMC searches cover gamma-delta pairing/generation, TCR language models/benchmarks and similarity/leakage benchmarks through 2026-10-06. This was a targeted update, not an exhaustive systematic review. Query strings, returned abstracts, hit counts and request metadata are cached under `reference_metadata/revision_bmc/`. The latest 100 records were retrieved for each broad search; hits outside this limit were not claimed to have been screened.','','Two relevant additions were selected after abstract screening: DTCR (2026, formal journal article), an epitope-conditioned generation task; and the germline-shortcut retrieval study (2026, explicitly a preprint), supporting attention to classical alignment and exposure controls. Neither is treated as a direct gamma-delta partner-recovery performance baseline.','','Current official BMC Bioinformatics submission guidelines were retrieved from `https://link.springer.com/journal/12859/submission-guidelines`; the legacy BMC URL redirected to the journal home page. The cached current page confirms double-line spacing, line/page numbers, editable TeX, no forced page breaks, figure-title/legend limits and the 20 MB additional-file limit.','','The search must be refreshed again if actual submission occurs substantially later. Public archiving and author declarations remain pending separately.']
    Path('paper/BMC_REFERENCE_AUDIT.md').write_text('\n'.join(lines)+'\n')
    print('Verified references',len(rows))
if __name__=='__main__':main()
