# Convert a symbol table (with parse tree) back to a script.
import lslfuncs
from lslcommon import Key, Vector, Quaternion
from lslparse import warning

class outscript(object):

    binary_operands = frozenset(('||','&&','^','|','&','==','!=','<','<=','>',
        '>=','<<','>>','+','-','*','/','%', '=', '+=', '-=', '*=', '/=','%=',
        ))
    extended_assignments = frozenset(('&=', '|=', '^=', '<<=', '>>='))
    unary_operands = frozenset(('NEG', '!', '~'))

    def Value2LSL(self, value):
        tvalue = type(value)
        if tvalue in (Key, unicode):
            pfx = sfx = ''
            if type(value) == Key:
                # Constants of type key can not be represented
                #raise lslfuncs.ELSLTypeMismatch
                # Actually they can be the result of folding.
                # On second thought, if we report the error, the location info
                # is lost. So we emit a warning instead, letting the compiler
                # report the error in the generated source.
                if self.globalmode and self.listmode:
                    warning('WARNING: Illegal combo: Key type inside a global list')
                if self.listmode or not self.globalmode:
                    if self.globalmode:
                        pfx = '(key)'
                    else:
                        pfx = '((key)'
                        sfx = ')'
            if '\t' in value:
                warning('WARNING: A string contains a tab. Tabs are expanded to four'
                        ' spaces by the viewer when copy-pasting the code.')
            return pfx + '"' + value.encode('utf8').replace('\\','\\\\') \
                .replace('"','\\"').replace('\n','\\n') + '"' + sfx
        if tvalue == int:
            if value < 0 and not self.globalmode and self.optsigns:
                #return '0x%X' % (value + 4294967296)
                return '((integer)' + str(value) + ')'
            return str(value)
        if tvalue == float:
            if self.optfloats and value.is_integer() and -2147483648.0 <= value < 2147483648.0:
                if self.globalmode and not self.listmode:
                    return str(int(value))
                elif not self.globalmode:
                    # Important inside lists!!
                    return '((float)' + str(int(value)) + ')'
            s = str(value)
            if s in ('inf', '-inf', 'nan'):
                return '((float)"' + s + '")' # this shouldn't appear in globals
            # Try to remove as many decimals as possible but keeping the F32 value intact
            exp = s.find('e')
            if ~exp:
                s, exp = s[:exp], s[exp:]
                if exp[1] == '+':
                    exp = exp[:1] + exp[2:]
                if '.' not in s:
                    # I couldn't produce one but it's assumed that if it happens,
                    # this code deals with it correctly
                    s += '.' # pragma: no cover
            else:
                if '.' not in s:
                    # This should never happen (Python should always return a point or exponent)
                    return s + '.' # pragma: no cover
                exp = ''

            # Shorten the float as much as possible.
            while s[-1] != '.' and lslfuncs.F32(float(s[:-1]+exp)) == value:
                s = s[:-1]
            if s[-1] != '.':
                news = s
                neg = ''
                if s[0] == '-':
                    news = s[1:]
                    neg = '-'
                # Try harder
                point = news.index('.') + 1 - len(news) # Remove point
                news = str(int(news[:point-1] + news[point:]) + 1).zfill(len(news)-1) # Increment
                news = news[:point + len(news)] + '.' + news[point + len(news):] # Reinsert point
                # Repeat the operation with the incremented number
                while news[-1] != '.' and lslfuncs.F32(float(neg+news[:-1]+exp)) == value:
                    news = news[:-1]
                if len(neg+news) < len(s) and lslfuncs.F32(float(neg+news[:-1]+exp)) == value:
                    # Success! But we try even harder.
                    if exp != '':
                        if news[2:3] == '.': # we converted 9.9... into 10.
                            newexp = 'e' + str(int(exp[1:])+1) # increase exponent
                            news2 = news[0] + '.' + news[1] + news[3:] # move dot to the left
                            while news2[-1] == '0': # remove trailing zeros
                                news2 = news2[:-1]
                            if len(neg+news2) < len(s) and lslfuncs.F32(float(neg+news2[:-1]+newexp)) == value:
                                news = news2
                                exp = newexp
                    s = neg+news
            if value >= 0 or self.globalmode or not self.optsigns:
                return s + exp
            return '((float)' + s + exp + ')'
        if tvalue == Vector:
            return '<' + self.Value2LSL(value[0]) + ', ' + self.Value2LSL(value[1]) \
                + ', ' + self.Value2LSL(value[2]) + '>'
        if tvalue == Quaternion:
            return '<' + self.Value2LSL(value[0]) + ', ' + self.Value2LSL(value[1]) \
                + ', ' + self.Value2LSL(value[2]) + ', ' + self.Value2LSL(value[3]) + '>'
        if tvalue == list:
            if value == []:
                return '[]'
            if len(value) < 5:
                self.listmode = True
                ret = '[' + self.Value2LSL(value[0])
                for elem in value[1:]:
                    ret += ', ' + self.Value2LSL(elem)
                ret += ']'
                self.listmode = False
                return ret
            ret = '\n'
            first = True
            self.indentlevel += 1
            for entry in value:
                if not first:
                    ret += self.dent() + ', '
                else:
                    ret += self.dent() + '[ '
                self.listmode = True
                ret += self.Value2LSL(entry) + '\n'
                self.listmode = False
                first = False
            self.indentlevel -= 1
            return ret + self.dent() + self.indent + ']'

        assert False, u'Value of unknown type in Value2LSL: ' + repr(value)

    def dent(self):
        return self.indent * self.indentlevel

    def OutIndented(self, node):
        if node['nt'] != '{}':
            self.indentlevel += 1
        ret = self.OutCode(node)
        if node['nt'] != '{}':
            self.indentlevel -= 1
        return ret

    def OutExprList(self, L):
        ret = ''
        if L:
            First = True
            for item in L:
                if not First:
                    ret += ', '
                ret += self.OutExpr(item)
                First = False
        return ret

    def OutExpr(self, expr):
        # Handles expression nodes (as opposed to statement nodes)
        nt = expr['nt']
        if 'ch' in expr:
            child = expr['ch']

        if nt == '()':
            return '(' + self.OutExpr(child[0]) + ')'

        if nt in self.binary_operands:
            return self.OutExpr(child[0]) + ' ' + nt + ' ' + self.OutExpr(child[1])

        if nt == 'IDENT':
            return expr['name']

        if nt == 'CONST':
            return self.Value2LSL(expr['value'])

        if nt == 'CAST':
            ret =  '(' + expr['t'] + ')'
            expr = child[0]
            if expr['nt'] in ('CONST', 'IDENT', 'V++', 'V--', 'VECTOR',
               'ROTATION', 'LIST', 'FIELD', 'PRINT', 'FUNCTION', '()'):
                return ret + self.OutExpr(expr)
            return ret + '(' + self.OutExpr(expr) + ')'

        if nt == 'LIST':
            self.listmode = True
            ret = '[' + self.OutExprList(child) + ']'
            self.listmode = False
            return ret

        if nt in ('VECTOR', 'ROTATION'):
            return '<' + self.OutExprList(child) + '>'

        if nt == 'FNCALL':
            return expr['name'] + '(' + self.OutExprList(child) + ')'

        if nt == 'PRINT':
            return 'print(' + self.OutExpr(child[0]) + ')'

        if nt in self.unary_operands:
            if nt == 'NEG':
                nt = '- '
            return nt + self.OutExpr(child[0])

        if nt == 'FLD':
            return self.OutExpr(child[0]) + '.' + expr['fld']

        if nt in ('V--', 'V++'):
            return self.OutExpr(child[0]) + ('++' if nt == 'V++' else '--')

        if nt in ('--V', '++V'):
            return ('++' if nt == '++V' else '--') + self.OutExpr(child[0])

        if nt in self.extended_assignments:
            lvalue = self.OutExpr(child[0])
            return lvalue + ' = ' + lvalue + ' ' + nt[:-1] + ' (' + self.OutExpr(child[1]) + ')'

        if nt == 'EXPRLIST':
            return self.OutExprList(child)

        assert False, 'Internal error: expression type "' + nt + '" not handled' # pragma: no cover

    def OutCode(self, node):
        nt = node['nt']
        if 'ch' in node:
            child = node['ch']
        else:
            child = None

        if nt == 'IF':
            ret = self.dent()
            while True:
                ret += 'if (' + self.OutExpr(child[0]) + ')\n' + self.OutIndented(child[1])
                if len(child) < 3:
                    return ret
                if child[2]['nt'] != 'IF':
                    ret += self.dent() + 'else\n' + self.OutIndented(child[2])
                    return ret
                ret += self.dent() + 'else '
                node = child[2]
                child = node['ch']
        if nt == 'WHILE':
            ret = self.dent() + 'while (' + self.OutExpr(child[0]) + ')\n'
            ret += self.OutIndented(child[1])
            return ret
        if nt == 'DO':
            ret = self.dent() + 'do\n'
            ret += self.OutIndented(child[0])
            return ret + self.dent() + 'while (' + self.OutExpr(child[1]) + ');\n'
        if nt == 'FOR':
            ret = self.dent() + 'for ('
            ret += self.OutExpr(child[0])
            ret += '; ' + self.OutExpr(child[1]) + '; '
            ret += self.OutExpr(child[2])
            ret += ')\n'
            ret += self.OutIndented(child[3])
            return ret
        if nt == '@':
            return self.dent() + '@' + node['name'] + ';\n'
        if nt == 'JUMP':
            return self.dent() + 'jump ' + node['name'] + ';\n'
        if nt == 'STSW':
            return self.dent() + 'state ' + node['name'] + ';\n'
        if nt == 'RETURN':
            if child:
                return self.dent() + 'return ' + self.OutExpr(child[0]) + ';\n'
            return self.dent() + 'return;\n'
        if nt == 'DECL':
            ret = self.dent() + node['t'] + ' ' + node['name']
            if child:
                ret += ' = ' + self.OutExpr(child[0])
            return ret + ';\n'
        if nt == ';':
            return self.dent() + ';\n'

        if nt in ('STDEF', '{}'):
            ret = ''
            if nt == 'STDEF':
                if node['name'] == 'default':
                    ret = self.dent() + 'default\n'
                else:
                    ret = self.dent() + 'state ' + node['name'] + '\n'

            ret += self.dent() + '{\n'
            self.indentlevel += 1
            for stmt in node['ch']:
                ret += self.OutCode(stmt)
            self.indentlevel -= 1
            return ret + self.dent() + '}\n'

        if nt == 'FNDEF':
            ret = self.dent()
            if node['t'] is not None:
                ret += node['t'] + ' '
            ret += node['name'] + '('
            ret += ', '.join(typ + ' ' + name for typ, name in zip(node['ptypes'], node['pnames']))
            return ret + ')\n' + self.OutCode(child[0])

        return self.dent() + self.OutExpr(node) + ';\n'

    def output(self, treesymtab, options = ('optsigns','optfloats')):
        # Build a sorted list of dict entries
        self.tree, self.symtab = treesymtab

        # Optimize signs
        self.optsigns = 'optsigns' in options
        self.optfloats = 'optfloats' in options

        ret = ''
        self.indent = '    '
        self.indentlevel = 0
        self.globalmode = False
        self.listmode = False
        for node in self.tree:
            self.globalmode = node['nt'] == 'DECL'
            ret += self.OutCode(node)
            self.globalmode = False

        return ret
