import operator as op
from random import randint

class GrammarParse():
    def __init__(self):
        pass

    def ScopeTransform(result):
        return lambda scope: Print(repr(scope))

    def NoLambda(self, result):
        return lambda scope: None

    def Noop(self, argument):
        return argument

    def Bits(self, result):
        value = list(map(lambda char: int(char), result[0]))
        return lambda scope: value

    def Name(self, result):
        return lambda scope: scope[result[0]]

    def Random(self, result):
        return lambda scope: [randint(0, 1)]

    def Input(self, result):
        return lambda scope: [GetInput(scope)]

    def Literal(self, result):
        return [result]

    def Arguments(self, result):
        arguments = result[1]
        if len(arguments):
            arguments = arguments[0]
            while (isinstance(arguments, list) and isinstance(arguments[-1], list)
                   and len(arguments[-1]) and len(arguments[-1][0]) == 2):
                last = arguments[-1]
                arguments = arguments[:-1] + [last[0][1]]
        if len(arguments) and not len(arguments[-1]):
            arguments = arguments[:-1]
        return lambda scope: arguments

    def Expression(self, result):
        length = len(result)
        if length == 1 and hasattr(result[0], "__call__"):
            result = result[0]
            while isinstance(result, list) and len(result) == 1:
                result = result[0]
            return result
        result = result[0][0]
        length = len(result)
        if length == 3:
            if (isinstance(result[0], basestring) and rOpenParenthesis.match(result[0])):
                return result[1]
            operator = result[1]
            if isinstance(operator, basestring) and rPlus.match(operator):
                return lambda scope: result[0](scope) + result[2](scope)
            if isinstance(operator, basestring) and rInfix.match(operator):
                if operator == "&":
                    return lambda scope: list(map(op.and_, result[0](scope), result[2](scope)))
                if operator == "|":
                    return lambda scope: list(map(op.or_, result[0](scope), result[2](scope)))
        if length == 2:
            operator = result[0]
            if isinstance(operator, basestring) and rPrefix.match(operator):
                if operator == "!":
                    return lambda scope: list(map(int, map(op.not_, result[1](scope))))
            operator = result[1]
            if isinstance(operator, basestring) and rPostfix.match(operator):
                if operator == "[h]":
                    return lambda scope: [result[0](scope)[0]]
                if operator == "[t]":
                    return lambda scope: [result[0](scope)[-1]]
            # Function call
            name = result[0]
            args = result[1]
            return lambda scope: name(scope)(list(map(lambda arg: arg[0][0](scope), args(scope))))
        if length == 1:
            return result[0]

    def Circuit(self, result):
        name = result[1]
        arguments = result[2]
        expression = result[4]
        return lambda scope: scope.set(name, lambda args: expression(Inject(Scope(scope), arguments(scope), args)))

    def Variable(self, result):
        name = result[1]
        value = result[3]
        return lambda scope: scope.set(name, value(scope))

    def Condition(self, result):
        condition = result[1]
        if_true = result[3]
        if_false = result[5]
        return lambda scope: if_true(scope) if condition(scope)[0] else if_false(scope)

    def Out(self, result):
        return lambda scope: Print(result[1](scope))

    def GetInput(self, scope):
        if not len(scope["input"]):
            scope["input"] = list(map(int, filter(lambda c: c == "0" or c == "1", raw_input(">>> "))))[::-1]
        return scope["input"].pop()


class Scope:
    def __init__(self, parent={}):
        self.parent = parent
        self.lookup = {}

    def __contains__(self, key):
        return key in self.parent or key in self.lookup

    def __getitem__(self, key):
        if key in self.lookup:
            return self.lookup[key]
        else:
            return self.parent[key]

    def __setitem__(self, key, value):
        if key in self.lookup:
            self.lookup[key] = value
        elif key in self.parent:
            self.parent[key] = value
        else:
            self.lookup[key] = value

    def __delitem__(self, key):
        if key in self.lookup:
            del self.lookup[key]
        else:
            del self.parent[key]

    def has(self, key):
        return key in self

    def get(self, key):
        return self[key]

    def set(self, key, value):
        self[key] = value

    def delete(self, key):
        del self[key]
