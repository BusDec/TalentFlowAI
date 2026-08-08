/* Shared recruitment funnel renderer (centered tapered SVG, no bars). */
function drawFunnel(containerId, values) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const stages = [
        ['received', 'Received'], ['document_verification', 'Doc Verification'],
        ['shortlisted', 'Shortlisted'], ['interview', 'Interview'],
        ['offered', 'Offered'], ['joined', 'Joined'],
    ];
    const colors = {
        received: '#4cc9f0', document_verification: '#7f5af0', shortlisted: '#9d4edb',
        interview: '#ffd166', offered: '#06d6a0', joined: '#2ec27e',
    };
    const maxVal = Math.max(1, ...stages.map(function (s) { return values[s[0]] || 0; }));
    const w = Math.max(el.clientWidth || 840, 600);
    const h = 300;
    const padL = 16, padR = 16, padT = 10, padB = 10;
    const labelW = 108;
    const chartW = w - padL - padR - labelW;
    const centerX = padL + chartW / 2;
    const stageH = (h - padT - padB) / stages.length;
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    el.innerHTML = '';
    el.appendChild(svg);

    function halfWidth(v) {
        return Math.max((v / maxVal) * (chartW / 2) * 0.92, 6);
    }

    stages.forEach(function (s, i) {
        const v = values[s[0]] || 0;
        const vn = i < stages.length - 1 ? (values[stages[i + 1][0]] || 0) : v;
        const y0 = padT + i * stageH + 2;
        const y1 = padT + (i + 1) * stageH - 2;
        const tw = halfWidth(v);
        // A funnel must taper: never let a later stage be drawn wider than the
        // current one, even when the raw counts are non-monotonic (e.g. more
        // interviews than shortlists in the data). True counts stay in labels.
        const bw = Math.min(Math.max(halfWidth(vn), 6), tw);

        const poly = document.createElementNS(NS, 'polygon');
        poly.setAttribute('points', [
            (centerX - tw).toFixed(1) + ',' + y0,
            (centerX + tw).toFixed(1) + ',' + y0,
            (centerX + bw).toFixed(1) + ',' + y1,
            (centerX - bw).toFixed(1) + ',' + y1,
        ].join(' '));
        poly.setAttribute('fill', colors[s[0]]);
        poly.setAttribute('opacity', '0.92');
        svg.appendChild(poly);

        const c = document.createElementNS(NS, 'text');
        c.setAttribute('x', centerX);
        c.setAttribute('y', (y0 + y1) / 2 + 4);
        c.setAttribute('text-anchor', 'middle');
        c.setAttribute('fill', '#0b0c1a');
        c.setAttribute('font-size', '12');
        c.setAttribute('font-weight', '800');
        c.textContent = v;
        svg.appendChild(c);

        const t = document.createElementNS(NS, 'text');
        t.setAttribute('x', centerX + chartW / 2 + 8);
        t.setAttribute('y', (y0 + y1) / 2 + 4);
        t.setAttribute('fill', '#c9cbe0');
        t.setAttribute('font-size', '10.5');
        t.textContent = s[1];
        svg.appendChild(t);
    });
}
