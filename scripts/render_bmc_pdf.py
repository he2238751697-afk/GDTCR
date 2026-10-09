#!/usr/bin/env python3
"""Readable BMC revision PDF with textual numeric math and numbered double spacing.

This is explicitly a ReportLab reading copy, not evidence of TeX compilation.
"""
import argparse,hashlib,json,re
from pathlib import Path
import render_manuscript_pdf as base
from reportlab.platypus import Paragraph
from reportlab.lib import colors
from reportlab.lib.units import mm
from pypdf import PdfReader


class NumberedParagraph(Paragraph):
    def draw(self):
        super().draw()
        if self.style.name=='Cell':return
        canvas=self.canv
        canvas.saveState();canvas.setFont('DejaVuSerif',6.5);canvas.setFillColor(colors.HexColor('#777777'))
        lines=getattr(getattr(self,'blPara',None),'lines',[])
        for i in range(len(lines)):
            canvas._bmc_line_number=getattr(canvas,'_bmc_line_number',0)+1
            canvas.drawRightString(-7*mm,self.height-self.style.fontSize-i*self.style.leading,str(canvas._bmc_line_number))
        canvas.restoreState()


class BMCReadingCopy(base.Renderer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for key in ('body','reference','caption','author'):
            self.styles[key].leading=2*self.styles[key].fontSize
        self.styles['cell'].leading=13

    def inline(self,text):
        def numeric(match):
            expression=match.group(1)
            plain=expression.replace(r'\pm',' ± ').replace(r'\times',' × ').replace(r'\%','%').replace(r'\{','(').replace(r'\}',')')
            superscripts=str.maketrans('0123456789-+','⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺')
            plain=re.sub(r'\^\{([-+\d]+)\}',lambda m:m[1].translate(superscripts),plain)
            plain=plain.replace('--','–')
            if re.fullmatch(r'[\d\s.,+\-±×%\[\]()⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺–]+',plain):return plain
            return match.group(0)
        text=re.sub(r'\$(.+?)\$',numeric,text,flags=re.S)
        return super().inline(text)

    def paragraphs(self,text):
        text=text.replace(r'\linenumbers','').replace(r'\doublespacing','')
        super().paragraphs(text)

    def footer(self,canvas,document):
        canvas.saveState();width,height=canvas._pagesize
        canvas.setFont('DejaVuSerif',7.2);canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(20*mm,13*mm,'BMC scientific revision | author declarations pending')
        canvas.drawRightString(width-20*mm,13*mm,str(document.page));canvas.restoreState()

    def figure(self,body):
        caption=base.command_value(body,'caption') or ''
        label=base.command_value(body,'label')
        match=re.search(r'\\includegraphics(?:\[[^]]*\])?\s*\{([^}]+)\}',body)
        if not match:raise ValueError('Figure requires a saved image')
        path=self.source.parent/match.group(1)
        if path.suffix=='.pdf' and path.with_suffix('.png').exists():path=path.with_suffix('.png')
        with base.PILImage.open(path) as im:width,height=im.size
        number=self.labels.get(label,str(self.figure_count+1))
        legend=NumberedParagraph('<b>Figure '+number+'.</b> '+self.inline(caption),self.styles['caption'])
        page_width,page_height=base.landscape(base.A4)
        usable_width=page_width-38*mm-12
        _,legend_height=legend.wrap(usable_width,page_height)
        usable_height=page_height-38*mm-12-legend_height-20
        if usable_height<120:raise ValueError('Figure legend leaves insufficient graphic space')
        scale=min(usable_width/width,usable_height/height)
        if len(self.flow)>=2 and isinstance(self.flow[-1],base.PageBreak) and isinstance(self.flow[-2],base.NextPageTemplate):
            self.flow=self.flow[:-2]
        self.flow.extend((base.NextPageTemplate('figure'),base.PageBreak(),
                          base.Image(str(path),width=width*scale,height=height*scale,hAlign='CENTER'),
                          base.Spacer(1,8),legend,base.NextPageTemplate('body'),base.PageBreak()))
        self.figure_count+=1

    def build(self,title):
        # The source remains authoritative; PDF metadata must not claim anonymity.
        super().build(title)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('paper/manuscript_bmc.tex'))
    parser.add_argument('--output',type=Path,default=Path('output/pdf/gdtcr_bmc_revision.pdf'))
    args=parser.parse_args()
    base.Paragraph=NumberedParagraph
    renderer=BMCReadingCopy(args.source,args.output,Path('tmp/pdfs/bmc_math'),False)
    title=renderer.parse(args.source.read_text());renderer.build(title)
    reader=PdfReader(args.output)
    from pypdf import PdfWriter
    writer=PdfWriter(clone_from=reader);writer.add_metadata({'/Author':'Author details pending confirmation','/Title':title})
    tmp=args.output.with_suffix('.tmp.pdf')
    with tmp.open('wb') as f:writer.write(f)
    tmp.replace(args.output);reader=PdfReader(args.output)
    text='\n'.join(page.extract_text() or '' for page in reader.pages)
    args.output.with_suffix('.txt').write_text(text)
    record={'renderer':'ReportLab BMC reading copy; native TeX compilation not asserted',
            'source':str(args.source),'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
            'pdf_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),'pages':len(reader.pages),
            'figures':renderer.figure_count,'tables':renderer.table_count,'references':len(renderer.references),
            'body_double_spaced':True,'line_and_page_numbers':True,'author_declarations_pending':True,
            'visual_inspection_required':True}
    args.output.with_suffix('.render.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))


if __name__=='__main__':main()
