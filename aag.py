""" Simple parser for Extended AIGER format for synthesis. """

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

class AAG(object):
    def __init__(self, aag_file):
        self.inputs = []
        self.latches = {} # latch -> latch_input
        self.latch_vars = []
        self.outputs = []
        self.and_gates = {} # and-gate -> inputs
        self.controllable = []

        header = [int(v) for v in aag_file.readline().strip().split(' ')[1:]]
        max_var, num_inputs, num_latches, num_outputs, num_and_gates = header
        self.max_var = max_var

        for i, line in enumerate(aag_file):
            if i < num_inputs: # inputs
                self.inputs.append(int(line))
            elif i < num_inputs + num_latches: # latches
                latch, linput = [int(v) for v in line.strip().split(' ')]
                self.latches[latch] = linput
                self.latch_vars.append(latch)
            elif i < num_inputs + num_latches + num_outputs: # output
                self.outputs.append(int(line))
            elif i < num_inputs + num_latches + num_outputs + num_and_gates: # and gates
                gate, lhs, rhs = [int(v) for v in line.strip().split(' ')]
                and_gate = (lhs, rhs)
                self.and_gates[gate] = and_gate
            elif line.startswith(('i', 'o', 'l')): # symbol table
                line = line.strip()
                left, right = line.split(' ', 1)
                index = int(left[1:])
                if right.startswith('controllable_'):
                    self.controllable.append(self.inputs[index])
                    line = line.replace('controllable_', '')
            elif line.strip() == 'c': # ignore comments
                break

        for v in self.controllable:
            self.inputs.remove(v)

        assert len(self.outputs) == 1

        # Create fake error latch
        self.error_latch = (max_var + 1) * 2
        self.latch_vars.append(self.error_latch)
        self.latches[self.error_latch] = self.outputs[0]
