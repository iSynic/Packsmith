"""Apply reviewed metadata-only patches to the isolated engine build, never references."""
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'assessment/references/xad-head'
    experiment=ROOT/'assessment/experiments/xad-windows/XADMaster'
    patches=ROOT/'app/patches';patches.mkdir(exist_ok=True)
    for name in ('XADStuffItParser.m','XADStuffIt5Parser.m','XADMacArchiveParser.m'):
        before=(source/name).read_text()
        after=before
        if name=='XADStuffItParser.m':
            for expr,key in (('CSUInt32BE(header+SITFH_MODDATE)','Modified'),('CSUInt32BE(header+SITFH_CREATIONDATE)','Created')):
                old=f'[NSDate XADDateWithTimeIntervalSince1904:{expr}],'
                after=after.replace(old,f'[NSNumber numberWithUnsignedInt:{expr}],@"Packsmith{key}1904",\n\t\t\t\t\t'+old)
        elif name=='XADStuffIt5Parser.m':
            for expr,key in (('modificationdate','Modified'),('creationdate','Created')):
                old=f'[NSDate XADDateWithTimeIntervalSince1904:{expr}],'
                after=after.replace(old,f'[NSNumber numberWithUnsignedInt:{expr}],@"Packsmith{key}1904",\n\t\t\t\t'+old)
        else:
            marker='[template setObject:[NSDate XADDateWithTimeIntervalSince1904:CSUInt32BE(bytes+91)] forKey:XADCreationDateKey];'
            after=after.replace(marker,'[template setObject:[NSNumber numberWithUnsignedInt:CSUInt32BE(bytes+91)] forKey:@"PacksmithCreated1904"];\n\t[template setObject:[NSNumber numberWithUnsignedInt:CSUInt32BE(bytes+95)] forKey:@"PacksmithModified1904"];\n\t'+marker)
        assert after!=before
        patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
        (patches/(name+'.patch')).write_text(patch,encoding='utf-8')
        (experiment/name).write_text(after,encoding='utf-8')

if __name__=='__main__':main()
