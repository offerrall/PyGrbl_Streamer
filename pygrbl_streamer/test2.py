import re
import math

class ArcToLinearConverter:

    def __init__(self, chord_tolerance: float = 0.01, max_segment_degrees: float = 5.0, decimals: int = 4):
        self.chord_tol = chord_tolerance
        self.max_seg_deg = max_segment_degrees
        self.decimals = decimals
        
        self.current_x = 0.0
        self.current_y = 0.0
        self.absolute_mode = True
        self.ijk_incremental = True
        
        self._num_re = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$')
    
    def reset_position(self, x=0.0, y=0.0):
        self.current_x = x
        self.current_y = y
    
    def convert_line(self, gcode_line):
        line = self._clean_line(gcode_line)
        if not line:
            return [gcode_line]
        
        tokens = self._parse_tokens(line)
        if not tokens:
            return [gcode_line]
        
        self._update_modal_state(tokens)
        
        gcode, params, other_words = self._extract_command_info(tokens)
        
        if gcode in (0, 1):
            self._update_position(params)
            return [gcode_line]
        
        if gcode in (2, 3):
            return self._convert_arc(gcode, params, other_words, line)
        
        return [gcode_line]
    
    def convert_file_content(self, content):
        lines = content.split('\n') if isinstance(content, str) else content
        result = []
        
        for line in lines:
            converted = self.convert_line(line)
            result.extend(converted)
        
        return result
    
    def _clean_line(self, line):
        if ';' in line:
            line = line[:line.index(';')]
        
        while '(' in line and ')' in line and line.index('(') < line.index(')'):
            start = line.index('(')
            end = line.index(')')
            line = line[:start] + line[end+1:]
        
        return line.strip()
    
    def _parse_tokens(self, line):
        tokens = []
        i = 0
        line = line.strip()
        
        while i < len(line):
            c = line[i].upper()
            if c.isalpha():
                j = i + 1
                while j < len(line) and (line[j].isdigit() or line[j] in '.+-eE'):
                    j += 1
                value = line[i+1:j].strip()
                tokens.append((c, value))
                i = j
            else:
                i += 1
        
        return tokens
    
    def _to_float(self, s):
        return float(s) if self._num_re.match(s) else float('nan')
    
    def _update_modal_state(self, tokens):
        for letter, value in tokens:
            if letter == 'G':
                try:
                    gcode = int(round(float(value)))
                    if gcode == 90:
                        self.absolute_mode = True
                    elif gcode == 91:
                        self.absolute_mode = False
                    elif gcode == 901:  # G90.1
                        self.ijk_incremental = False
                    elif gcode == 911:  # G91.1
                        self.ijk_incremental = True
                except:
                    continue
    
    def _extract_command_info(self, tokens):
        gcode = None
        params = {}
        other_words = []
        
        for letter, value in tokens:
            if letter == 'G':
                try:
                    gcode = int(round(float(value)))
                except:
                    pass
            elif letter in ('X', 'Y', 'I', 'J', 'R', 'F'):
                fv = self._to_float(value)
                if not math.isnan(fv):
                    params[letter] = fv
            else:
                other_words.append(letter + value)
        
        return gcode, params, other_words
    
    def _update_position(self, params):
        x = params.get('X')
        y = params.get('Y')
        
        if x is None and y is None:
            return
        
        if self.absolute_mode:
            if x is not None:
                self.current_x = x
            if y is not None:
                self.current_y = y
        else:
            if x is not None:
                self.current_x += x
            if y is not None:
                self.current_y += y
    
    def _convert_arc(self, gcode, params, other_words, original_line):
        cw = (gcode == 2)

        if 'X' not in params and 'Y' not in params:
            return [original_line]

        if self.absolute_mode:
            end_x = params.get('X', self.current_x)
            end_y = params.get('Y', self.current_y)
        else:
            end_x = self.current_x + params.get('X', 0.0)
            end_y = self.current_y + params.get('Y', 0.0)
        
        start = (self.current_x, self.current_y)
        end = (end_x, end_y)

        if 'I' in params or 'J' in params:
            i = params.get('I', 0.0)
            j = params.get('J', 0.0)
            segments = self._segment_arc_ij(start, end, cw, i, j)
        elif 'R' in params:
            segments = self._segment_arc_r(start, end, cw, params['R'])
        else:
            return [original_line]

        result = []

        for word in other_words:
            if word[0] in ('S', 'M', 'F'):
                result.append(word)

        result.extend(segments)
        self.current_x = end_x
        self.current_y = end_y
        
        return result
    
    def _segment_arc_ij(self, start, end, cw, i, j):
        sx, sy = start
        ex, ey = end

        if self.ijk_incremental:
            cx = sx + i
            cy = sy + j
        else:
            cx = i
            cy = j

        radius = math.hypot(sx - cx, sy - cy)
        if radius <= 1e-9:
            return [self._format_g1(ex, ey)]

        start_angle = math.atan2(sy - cy, sx - cx)
        end_angle = math.atan2(ey - cy, ex - cx)

        sweep = self._normalize_angle(end_angle - start_angle)
        if cw and sweep > 0:
            sweep -= 2 * math.pi
        if not cw and sweep < 0:
            sweep += 2 * math.pi
        
        return self._generate_segments(cx, cy, radius, start_angle, sweep, (ex, ey))
    
    def _segment_arc_r(self, start, end, cw, R):
        sx, sy = start
        ex, ey = end
        
        dx = ex - sx
        dy = ey - sy
        chord_length = math.hypot(dx, dy)
        
        if chord_length <= 1e-12:
            return [self._format_g1(ex, ey)]
        
        radius = abs(R)
        if radius < chord_length / 2.0:
            radius = chord_length / 2.0

        mx = (sx + ex) / 2.0
        my = (sy + ey) / 2.0

        try:
            h = math.sqrt(max(0.0, radius*radius - (chord_length/2.0)**2))
        except ValueError:
            h = 0.0

        nx = -dy / chord_length
        ny = dx / chord_length

        cx1, cy1 = mx + nx*h, my + ny*h
        cx2, cy2 = mx - nx*h, my + ny*h
        
        def calc_sweep(cx, cy):
            start_angle = math.atan2(sy - cy, sx - cx)
            end_angle = math.atan2(ey - cy, ex - cx)
            sweep = self._normalize_angle(end_angle - start_angle)
            if cw and sweep > 0:
                sweep -= 2 * math.pi
            if not cw and sweep < 0:
                sweep += 2 * math.pi
            return start_angle, sweep
        
        a1, s1 = calc_sweep(cx1, cy1)
        a2, s2 = calc_sweep(cx2, cy2)
        
        if R > 0:
            if abs(s1) <= abs(s2):
                cx, cy, start_angle, sweep = cx1, cy1, a1, s1
            else:
                cx, cy, start_angle, sweep = cx2, cy2, a2, s2
        else:
            if abs(s1) >= abs(s2):
                cx, cy, start_angle, sweep = cx1, cy1, a1, s1
            else:
                cx, cy, start_angle, sweep = cx2, cy2, a2, s2
        
        return self._generate_segments(cx, cy, radius, start_angle, sweep, (ex, ey))
    
    def _generate_segments(self, cx, cy, radius, start_angle, sweep, end_point):
        if radius <= 1e-9:
            return [self._format_g1(*end_point)]
        
        arg = 1.0 - (self.chord_tol / radius)
        arg = min(1.0, max(-1.0, arg))
        
        if -1.0 <= arg <= 1.0:
            theta_tol = 2.0 * math.acos(arg)
        else:
            theta_tol = math.radians(self.max_seg_deg)
        
        theta_max = min(theta_tol, math.radians(self.max_seg_deg))
        steps = max(2, int(math.ceil(abs(sweep) / max(theta_max, 1e-6))))
        
        segments = []
        for i in range(1, steps):
            angle = start_angle + sweep * (i / steps)
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            segments.append(self._format_g1(x, y))
        
        segments.append(self._format_g1(*end_point))
        
        return segments
    
    def _format_g1(self, x, y):
        return f"G1 X{x:.{self.decimals}f} Y{y:.{self.decimals}f}"
    
    @staticmethod
    def _normalize_angle(angle):
        while angle <= -math.pi:
            angle += 2 * math.pi
        while angle > math.pi:
            angle -= 2 * math.pi
        return angle