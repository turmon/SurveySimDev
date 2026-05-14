# Generated file

class StarInfoTreeMixin:

    def sr_H2O_no(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["H2O"]
        vals = ["no"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_H2O_yes_CH4_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["H2O", "CH4"]
        vals = ["yes", "yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_H2O_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["H2O"]
        vals = ["yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_O2_high(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["O2"]
        vals = ["high"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_O2_medium(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["O2"]
        vals = ["medium"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_O2_no(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["O2"]
        vals = ["no"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_CH4_no(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["CH4"]
        vals = ["no"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_CH4_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["CH4"]
        vals = ["yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_CH4_yes_CO2_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["CH4", "CO2"]
        vals = ["yes", "yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_ok(self, mode=None, retrieval=None):
        # ensure there was a char
        if self.n_char_ok[mode] == 0:
            return False
        return True


    def sr_CO2_no(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["CO2"]
        vals = ["no"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_CO2_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["CO2"]
        vals = ["yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_press_low(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["press"]
        vals = ["low"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_press_high(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["press"]
        vals = ["high"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_press_low(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["press"]
        vals = ["low"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_press_high(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["press"]
        vals = ["high"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_O3_no(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["O3"]
        vals = ["no"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv


    def sr_O3_yes(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = ["O3"]
        vals = ["yes"]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv

