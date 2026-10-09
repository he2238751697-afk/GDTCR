#!/usr/bin/env python3
"""Audit frozen numbers, reference metadata, assets and final PDF placement."""
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
from collections import defaultdict
import pdfplumber
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper/final_submission"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main():
    records = []
    def check(name, ok, evidence):
        if not ok:
            raise AssertionError(f"{name}: {evidence}")
        records.append({"check": name, "passed": True, "evidence": evidence})

    frozen = json.loads((OUT / "scientific_freeze.json").read_text())
    for name, expected in frozen["files"].items():
        check("Frozen file: " + name, sha(ROOT / name) == expected, expected)
    groups = defaultdict(list)
    with (ROOT / "paper/results/bmc/tables/primary_query_results.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            groups[row["split_seed"], row["condition"], row["training_seed"],
                   row["direction"]].append(row)
    summaries = {}
    with (ROOT / "paper/results/v2/tables/primary_descriptives.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            summaries[row["model"],row["direction"],row["metric"]] = row
    for condition in ("paired","constant","random","shuffled"):
        for direction in ("gamma_to_delta","delta_to_gamma","equal_direction_macro"):
            for metric in ("query_mean_nll","coverage","likelihood|hit_at_5"):
                splits=[]
                for split in ("17","3407","2026"):
                    fitted=[]
                    for seed in ("3407","3508"):
                        directions=("gamma_to_delta","delta_to_gamma") if direction=="equal_direction_macro" else (direction,)
                        fitted.append(statistics.mean(statistics.mean(float(r[metric])
                            for r in groups[split,condition,seed,d]) for d in directions))
                    splits.append(statistics.mean(fitted))
                expected=summaries[condition,direction,metric]
                check(f"Query reconstruction: {condition}/{direction}/{metric}",
                      abs(statistics.mean(splits)-float(expected["mean"]))<1e-12
                      and abs(statistics.stdev(splits)-float(expected["sd_of_three_split_means"]))<1e-12,
                      "primary_query_results.tsv -> seed means -> split means and sample SD")
    text=(ROOT/"paper/manuscript_bmc.tex").read_text()
    supplement=(ROOT/"paper/supplementary_methods_bmc.tex").read_text()
    citations=[]
    for group in re.findall(r"\\cite\{([^}]+)\}",text):
        for key in group.split(","):
            if key not in citations:citations.append(key)
    bib=re.findall(r"\\bibitem\{([^}]+)\}",text)
    check("References numbered by first citation",citations==bib,"manuscript TeX")
    refs=json.loads((ROOT/"paper/references_bmc.json").read_text())["references"]
    for ref in refs:
        p=ROOT/ref["verification_source"]
        check("Reference metadata checksum: "+ref["key"],sha(p)==ref["verification_sha256"],str(p.relative_to(ROOT)))
        item=re.search(r"\\bibitem\{"+ref["key"]+r"\}(.*?)(?=\\bibitem|\\end\{thebibliography\})",text,re.S)[1]
        check("Reference DOI: "+ref["key"],ref["doi"] in item,ref["doi"])
        check("Reference year: "+ref["key"],str(ref["year"]) in item,"Verified issue year; preprints explicitly labeled")
        check("Reference volume/pages: "+ref["key"],
              (not ref.get("volume") or str(ref["volume"]) in item)
              and (not ref.get("pages_or_article") or ref["pages_or_article"] in ("DOI identifies record","not assigned")
                   or ref["pages_or_article"].replace("–","--").replace("-","") in item.replace("-","")
                   or ref["pages_or_article"].replace("–","-").replace("-","") in item.replace("-","")),
              "references_bmc.json volume and article/page identifiers")
    additional=list(dict.fromkeys(int(v) for v in re.findall(r"Additional file ([1-6])",text)))
    check("Additional files first cited in order",additional==list(range(1,7)),additional)
    placement=[]
    for source,body,name in (("paper/manuscript_bmc.tex",text,"gdtcr_bmc_revision"),
                             ("paper/supplementary_methods_bmc.tex",supplement,"additional_file_1_bmc")):
        labels=re.findall(r"\\label\{([^}]+)\}",body)
        check("Unique labels: "+source,len(labels)==len(set(labels)),labels)
        check("Resolved references: "+source,set(re.findall(r"\\ref\{([^}]+)\}",body))<=set(labels),"TeX")
        record=json.loads((ROOT/"output/pdf"/(name+".render.json")).read_text())
        check("Compiled source hash: "+name,sha(ROOT/source)==record["source_sha256"],"native compilation manifest")
        pdf=ROOT/"output/pdf"/(name+".pdf")
        check("Compiled PDF hash: "+name,sha(pdf)==record["pdf_sha256"],"native compilation manifest")
        fonts=subprocess.check_output(["pdffonts",str(pdf)],text=True).splitlines()[2:]
        check("All fonts embedded, no Type 3: "+name,
              all(re.search(r"\byes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$",line)
                  and "Type 3" not in line for line in fonts),"pdffonts")
        with pdfplumber.open(pdf) as doc:
            pages=[p.extract_text() or "" for p in doc.pages]
            for page in doc.pages:
                check(f"Page bounds {name}/{page.page_number}",
                      all(-.5<=c["x0"]<=c["x1"]<=page.width+.5
                          and -.5<=c["top"]<=c["bottom"]<=page.height+.5 for c in page.chars),
                      "Character boxes inside media box; visual review checks actual overlap")
            for kind,key,prefix in (("Figure","figure","fig:"),("Table","table","tab:")):
                for label in (v for v in labels if v.startswith(prefix)):
                    aux=(ROOT/"output/pdf/tex"/name/(Path(source).stem+".aux")).read_text()
                    match=re.search(r"\\newlabel\{"+re.escape(label)+r"\}\{\{([^}]+)\}\{([^}]+)\}",aux)
                    check("Compiled label "+label,bool(match),str(match))
                    number,page=match[1],int(match[2])
                    occurrences=[]
                    for i,content in enumerate(pages,1):
                        if re.search(kind+r"\s*"+re.escape(number)+r"(?![0-9A-Za-z:])",content):
                            occurrences.append(i)
                    caption_pages=[i for i,content in enumerate(pages,1)
                                   if re.search(kind+r"\s*"+re.escape(number)+r":",content)]
                    check("Single intact caption "+label,caption_pages==[page],caption_pages)
                    placement.append({"document":name,"kind":kind,"label":label,
                                      "number":number,"first_citation_page":min(occurrences) if occurrences else None,
                                      "caption_page":page})
            check("No broken reference/glyph marker "+name,
                  all(not any(t in p for t in ("??","\ufffd","PERCENTTOKEN","XMLTOKEN")) for p in pages),
                  "extracted text, supplemented by visual review")
    assets=[]
    for pdf in sorted((ROOT/"paper/results/bmc/figures").glob("*.pdf")):
        png=pdf.with_suffix(".png");svg=pdf.with_suffix(".svg")
        with Image.open(png) as im:
            dpi=im.info.get("dpi",(0,0));dims=im.size
        check("Editable and high-resolution assets: "+pdf.stem,svg.is_file() and min(dpi)>=299,
              {"pixels":dims,"dpi":dpi})
        assets.append({"figure":pdf.stem,"pdf_sha256":sha(pdf),"svg_sha256":sha(svg),
                       "png_sha256":sha(png),"pixels":dims,"dpi":dpi})
    write("placement_audit.json",placement)
    write("crossref_numerical_audit.json",{"passed":True,"checks":len(records),
          "frozen_files":len(frozen["files"]),"query_rows":sum(map(len,groups.values())),
          "references":len(refs),"records":records,"assets":assets,
          "scientific_discrepancies_found":[],"administrative_blockers":"paper/BMC_AUTHOR_ITEMS.md"})
    print(json.dumps({"passed":True,"checks":len(records),"placement":placement},indent=2))


if __name__=="__main__":
    main()
