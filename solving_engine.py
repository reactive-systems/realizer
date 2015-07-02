""" Implementation of the backward fixpoint algorithm for safety games. """

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

import pycudd

CUDD_REORDER_SAME = 0
CUDD_REORDER_RANDOM = 2
CUDD_REORDER_SIFT = 4
CUDD_REORDER_SIFT_CONVERGE = 5
CUDD_REORDER_LAZY_SIFT = 20

class BDDSolver(object):
    def __init__(self, aag, remove_latch_copies=True, lazy_transition_function=False, use_automatic_reordering=True):
        self.aag = aag

        # Initialize CUDD
        self.mgr = pycudd.DdManager()
        self.mgr.SetDefault()
        if use_automatic_reordering:
            self.mgr.AutodynEnable(CUDD_REORDER_LAZY_SIFT)

        # Helper data structures
        self.varcount = 0
        self.varmapping = {} # var(num) => mgr index
        self.primedmapping = {} # var(num) => mgr index
        self.reversemapping = {} # index => var(num)
        self.current = []
        self.primed = []
        self.exiscube = None # cube containing existential variables
        self.univcube = None # cube containing universal variables
        self.buildcache = {} # node(num) => node(bdd)
        self.replacement_vector = None

        # Remove latches that just copy the last input?
        self.remove_latch_copies = remove_latch_copies
        if self.remove_latch_copies:
            self.latch_mapping = {}

            for latch in self.aag.latches:
                var = self.aag.latches[latch]
                if var in self.aag.inputs + self.aag.controllable:
                    self.latch_mapping[latch] = var

        self.lazy_transition_function = lazy_transition_function

        if self.lazy_transition_function:
            self.transition_function = {}
            self.latch_vars = self.aag.latch_vars
        else:
            # micro optimization, make fake error latch the latch that is processed first
            self.latch_vars = self.aag.latch_vars[-1:] + self.aag.latch_vars[0:-1]

    def isRealizable(self):
        transition_function = self.getTransitionFunction()
        initial_states = self.getInitialStates()

        self.finalize()

        safe_states = self.getSafeStates()
        zero_assignment = self.IntArrayFromList([0]*self.varcount)[0]

        fixpoint = None
        i = 0
        while safe_states != fixpoint:
            i += 1
            print("Step {}".format(i))
            fixpoint = safe_states
            safe_states &= self.preSystem(safe_states, transition_function)

            # check if safe states reachable from initial
            # can evaluate on zero assignemnt as safe_states contains only latches
            if not bool(safe_states.Eval(zero_assignment)):
                return False

        return True

    def getSafeStates(self):
        # returns BDD representing the safe states
        return ~self.getVariable(self.aag.error_latch)

    def getSafeOut(self):
        # returns BDD representing the safe output
        assert len(self.aag.outputs) == 1
        return ~self.buildTransitionFunction(self.aag.outputs[0])

    def getStates(self, bdd):
        if self.lazy_transition_function:
            bdd = bdd.VectorCompose(self.replacement_vector)

        # existential abstraction
        bdd = bdd.ExistAbstract(self.exiscube)

        # universal abstraction
        bdd = bdd.UnivAbstract(self.univcube)

        return bdd

    def getInitialStates(self):
        # returns BDD representing the initial states
        initial = self.mgr.One()
        for latch in [self.getVariable(v) for v in self.latch_vars]:
            initial = initial & ~latch
        return initial

    def getTransitionFunction(self):
        # returns BDD representing the transition function
        formula = []
        for latch in self.latch_vars:
            self.getVariable(latch)

            if not self.lazy_transition_function:
                # if latch copies the value of an input/controllable, do not include them in the transition function
                if self.remove_latch_copies and latch in self.latch_mapping:
                    self.buildTransitionFunction(self.aag.latches[latch])
                    continue

            if not self.lazy_transition_function:
                primed = self.mgr.ReadVars(self.primedmapping[latch])
                formula.append(primed.Xnor(self.buildTransitionFunction(self.aag.latches[latch])))
            else:
                self.transition_function[latch] = self.buildTransitionFunction(self.aag.latches[latch])

        if not formula:
            return self.mgr.One()

        while len(formula) > 1:
            a = formula.pop(0)
            b = formula.pop(0)
            formula.append(a & b)

        return formula[0]

    def finalize(self):
        if not self.lazy_transition_function:
            # Set the variable Map (mapping between primed and unprimed)
            size = len(self.latch_vars)

            current_array = pycudd.DdArray(size)
            primed_array = pycudd.DdArray(size)
            for latch in self.latch_vars:
                current_array.Push(self.mgr.ReadVars(self.varmapping[latch]))

                # optimize the copy latches: instead of mapping them to their primed variants, we map them to the variable which they should copy
                if self.remove_latch_copies and latch in self.latch_mapping:
                    primed_array.Push(self.mgr.ReadVars(self.varmapping[self.latch_mapping[latch]]))
                else:
                    primed_array.Push(self.mgr.ReadVars(self.primedmapping[latch]))

            self.mgr.SetVarMap(current_array, primed_array, size)
        else:
            replacements = []
            for i in range(self.varcount):
                assert i in self.reversemapping
                var = self.reversemapping[i]
                if var in self.transition_function:
                    replacements.append(self.transition_function[var])
                else:
                    replacements.append(self.mgr.ReadVars(i))

            assert len(replacements) == self.varcount
            self.replacement_vector, size = self.DdArrayFromList(replacements)
            assert size == len(replacements)

        # build the existential and universal cubes

        # get controllable inputs and latches
        existential = self.getIndicesFromVariables(self.aag.controllable, self.varmapping)
        if not self.lazy_transition_function:
            existential.extend(self.getIndicesFromVariables(self.latch_vars, self.primedmapping))

        # build index cube
        array, size = self.IntArrayFromList(existential)
        self.exiscube = self.mgr.IndicesToCube(array, size)

        # input cube
        self.univcube = self.cubeFromVariables(self.aag.inputs, self.varmapping)

        # remove build cache
        del self.buildcache


    def getVariable(self, var):
        assert var % 2 == 0

        if var in self.varmapping:
            return self.mgr.ReadVars(self.varmapping[var])
        else:
            # create current state variable
            bdd_var = self.mgr.NewVar()
            self.varmapping[var] = self.varcount
            self.reversemapping[self.varcount] = var
            self.current.append(bdd_var)
            self.varcount += 1

            if var in self.aag.inputs:
                self.mgr.SetPiVar(self.varcount-1)
            self.mgr.SetPsVar(self.varcount-1)

            if var in self.latch_vars and not self.lazy_transition_function:
                # create primed next state variable
                primed_var = self.mgr.NewVar()
                self.primedmapping[var] = self.varcount
                self.primed.append(primed_var)
                self.varcount += 1

                self.mgr.SetPairIndex(self.varcount-2, self.varcount-1)
                self.mgr.SetNsVar(self.varcount-1)

            return bdd_var

    def buildTransitionFunction(self, var):
        negated = False
        if var % 2 == 1:
            negated = True
            var -= 1

        formula = None
        if var in self.buildcache:
            formula = self.buildcache[var]
        elif var in self.aag.and_gates:
            lhs = self.buildTransitionFunction(self.aag.and_gates[var][0])
            rhs = self.buildTransitionFunction(self.aag.and_gates[var][1])
            formula = lhs & rhs
        elif var in self.aag.inputs + self.aag.controllable + self.aag.latch_vars:
            formula = self.getVariable(var)
        elif var == 0:
            formula = self.mgr.Zero()
        else:
            assert False

        if not var in self.buildcache:
            self.buildcache[var] = formula

        if negated:
            return ~formula
        else:
            return formula

    def preSystem(self, safe_states, transition_function):
        if not self.lazy_transition_function:
            # prime latches
            next_safe = safe_states.VarMap()
            # combinde with transition function
            bdd = next_safe.AndAbstract(transition_function, self.exiscube)
            #bdd = next_safe & transition_function
            #bdd = bdd.ExistAbstract(self.exiscube)
        else:
            next_safe = safe_states
            bdd = safe_states.VectorCompose(self.replacement_vector)
            bdd = bdd.ExistAbstract(self.exiscube)

        # abstracting inputs
        bdd = bdd.UnivAbstract(self.univcube)

        return bdd

    def IntArrayFromList(self, index_list):
        size = len(index_list)
        array = pycudd.IntArray(size)
        for i in range(size):
            array[i] = index_list[i]

        return array, size

    def DdArrayFromList(self, index_list):
        size = len(index_list)
        array = pycudd.DdArray(size)
        for i in range(size):
            array[i] = index_list[i]

        return array, size

    def getIndicesFromVariables(self, variables, mapping):
        result = []
        for var in variables:
            if var in mapping:
                i = mapping[var]
                result.append(i)
        return result

    def cubeFromVariables(self, variables, mapping):
        indices = self.getIndicesFromVariables(variables, mapping)
        array, size = self.IntArrayFromList(indices)
        return self.mgr.IndicesToCube(array, size)
