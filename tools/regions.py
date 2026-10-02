"""The four retail releases of Rhythm Heaven Fever and where their pieces moved.

All four are disc version 0.  They share one compiled program; every address
the patches use is either carried over from the USA release by a masked
signature search (see sig.py and src/gen_gc.py) or is a Vague Rant site.
"""
REGIONS = {
    'SOME01': dict(label='Rhythm Heaven Fever (USA)', short='USA', version=0),
    'SOMP01': dict(label='Beat the Beat: Rhythm Paradise (Europe)', short='Europe', version=0),
    'SOMJ01': dict(label='Minna no Rhythm Tengoku (Japan)', short='Japan', version=0),
    'SOMK01': dict(label='Rhythm World Wii (Korea)', short='Korea', version=0),
}

# retail DOL sizes, to give a clear error on someone else's modified dump
DOL_SIZES = {'SOME01': 3296160, 'SOMP01': 3302048, 'SOMJ01': 3326048, 'SOMK01': 3279328}
