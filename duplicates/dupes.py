from collections import defaultdict, deque
from contextlib import ExitStack
import os
from pathlib import Path
from typing import Any, Callable, Iterable
from uuid import uuid1

from .bufferediofile import BufferedIOFile

def linkdupes(rootpath: Path) -> None:
    dupes = finddupes(rootpath)
    for setoffiles in dupes:
        fileiterator = iter(setoffiles)
        filetokeep = next(fileiterator).path
        for filetolink in fileiterator:
            replacewithlink(filetokeep, filetolink.path)

def finddupes(rootpath: Path) -> set[frozenset[BufferedIOFile]]:
    samesizefiles = _filesofsamesize(rootpath)
    nohardlinks = {_drophardlinks(files) for files in samesizefiles}
    dupes = set()
    for fileset in nohardlinks:
        fileobjects = {BufferedIOFile(filepath) for filepath in fileset}
        with ExitStack() as stack:
            _ = [stack.enter_context(file.open()) for file in fileobjects]
            dupes |= comparefilecontents({frozenset(fileobjects)})
    return dupes

def replacewithlink(keep: Path, replace: Path) -> None:
    def _extendpath(self: Path, string: Any) -> Path:
        return Path(''.join((str(self),str(string))))
    Path.__add__ = _extendpath

    tmplink = replace + '_' + uuid1()
    tmplink.hardlink_to(keep)
    os.replace(tmplink, replace)

def comparefilecontents(setstocompare: set[frozenset[BufferedIOFile]]) -> set[frozenset[BufferedIOFile]]:
    newsets = set()
    for setoffiles in setstocompare:
        newsets |= _comparefilechunk(setoffiles)
    try:
        return comparefilecontents(newsets)
    except EOFError:
        return set(files for files in newsets)

def _sift(iterator: Iterable, siftby: Callable, onfail: Exception = ValueError) -> set[frozenset]:
    """Sifts an iterator and returns only those sets of values which share a common property
    - iterator: the iterator to sift
    - siftby: a Callable which when applied to each item in iterator returns the property to be used for sifting
    - onfail: the exception type to raise if siftby returns a Falsey result. Default: Value Error

    Returns: A set of frozensets, where all elements of each frozenset share the same property.
    Only sets with more than one item are returned - unique items are sifted out.
    """
    tmpdict = defaultdict(set)
    for item in iterator:
        idx = siftby(item)
        if idx: 
            tmpdict[idx].add(item)
        else:
            raise onfail
    return {frozenset(group) for group in tmpdict.values() if len(group) > 1}

def _filesofsamesize(pathtosearch: Path) -> set[frozenset]:
    def _filepaths(in_path: Path):
        for root, dirs, files in in_path.walk():
            for file in files:
                filepath = root / file
                yield filepath
    
    dupes = _sift(_filepaths(pathtosearch), lambda p: p.stat().st_size)
    return dupes

def _comparefilechunk(filestocompare: frozenset[BufferedIOFile]) -> set[frozenset[BufferedIOFile]]:
    possibleduplicates = _sift(filestocompare, lambda f: f.readchunk(), EOFError)
    return possibleduplicates
    
def _drophardlinks(filestocheck: frozenset[Path]) -> frozenset[Path]:    
    uniqueinos = defaultdict(lambda: deque(maxlen=1))
    for file in filestocheck:
        id = file.stat().st_ino
        uniqueinos[id] = file
    return frozenset(uniqueinos.values())