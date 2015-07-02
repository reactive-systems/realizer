#!/usr/bin/env python

"""
Copyright (c) 2014-2015, Leander Tentrup, Saarland University <tentrup@react.uni-saarland.de>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
"""

import argparse
import multiprocessing
import sys

from aag import AAG
from solving_engine import BDDSolver


def solve(pid, aiger_instance, result_queue=None):
    if pid == 0:
        solver = BDDSolver(aiger_instance, lazy_transition_function=True)
    else:
        solver = BDDSolver(aiger_instance, lazy_transition_function=False)

    is_realizable = solver.isRealizable()
    if result_queue:
        result_queue.put(is_realizable)
    else:
        return is_realizable

def main():
    sys.setrecursionlimit(100000)

    parser = argparse.ArgumentParser()
    parser.add_argument('file', metavar='file_name', type=argparse.FileType('r'),
                        help='Safety game in AAG format')
    parser.add_argument('-p', '--parallel', dest='parallel', action='store_true',
                        help='enables parallel solving')
    parser.add_argument('-m', '--monolithic', dest='monolithic', action='store_true',
                        help='enables monolithic transition function')

    args = parser.parse_args()

    aiger_instance = AAG(args.file)

    if args.parallel:
        q = multiprocessing.Queue()

        processes = [multiprocessing.Process(target=solve, args=(i, aiger_instance, q)) for i in range(2)]
        for process in processes:
            process.daemon = True
            process.start()

        is_realizable = q.get()

    else:
        if args.monolithic:
            is_realizable = solve(1, aiger_instance)
        else:
            is_realizable = solve(0, aiger_instance)

    if is_realizable:
        print('realizable')
        exit(10)
    else:
        print('unrealizable')
        exit(20)

if __name__ == "__main__":
    main()
