(function(){
  var nodes = Array.prototype.slice.call(document.querySelectorAll('.rail-node'));
  var sections = nodes.map(function(n){ return document.getElementById(n.dataset.target); });
  var fill = document.getElementById('railFill');
  var wrap = document.querySelector('.rail-track-wrap');
  if (!fill || !wrap || !nodes.length) return;

  function maxScroll(){
    var doc = document.documentElement;
    return Math.max(1, doc.scrollHeight - window.innerHeight);
  }

  function sectionProgress(sec){
    if (!sec) return 0;
    var top = sec.getBoundingClientRect().top + window.scrollY;
    return Math.min(1, Math.max(0, top / maxScroll()));
  }

  function layoutNodes(){
    var h = wrap.clientHeight;
    nodes.forEach(function(node, i){
      var pos = sectionProgress(sections[i]);
      // Keep first and last readable if measurement fails
      if (!sections[i]) pos = nodes.length > 1 ? (i / (nodes.length - 1)) : 0;
      node.style.top = (pos * h) + 'px';
      node.dataset.progress = String(pos);
    });
  }

  function setActive(idx){
    nodes.forEach(function(n, i){
      if (i === idx) n.classList.add('active');
      else n.classList.remove('active');
    });
  }

  function activeFromScroll(){
    var mid = window.innerHeight * 0.4;
    var best = 0;
    var bestDist = Infinity;
    sections.forEach(function(sec, i){
      if (!sec) return;
      var r = sec.getBoundingClientRect();
      var dist = (r.top <= mid && r.bottom >= mid) ? 0 : Math.abs(r.top - mid);
      if (dist < bestDist){
        bestDist = dist;
        best = i;
      }
    });
    setActive(best);
    return best;
  }

  function updateProgress(){
    var p = Math.min(1, Math.max(0, (window.scrollY || document.documentElement.scrollTop) / maxScroll()));
    var active = activeFromScroll();
    // Fill follows scroll, but never sits behind the active section's node
    var nodePos = parseFloat(nodes[active].dataset.progress || '0');
    var fillP = Math.max(p, nodePos);
    if (window.innerWidth <= 900){
      fill.style.width = (fillP * 100) + '%';
      fill.style.height = '100%';
    } else {
      fill.style.height = (fillP * 100) + '%';
      fill.style.width = '100%';
    }
  }

  var ticking = false;
  function onScroll(){
    if (!ticking){
      window.requestAnimationFrame(function(){ updateProgress(); ticking = false; });
      ticking = true;
    }
  }

  window.addEventListener('resize', function(){ layoutNodes(); updateProgress(); });
  window.addEventListener('scroll', onScroll, { passive: true });
  // Images can shift layout; relayout once after load
  window.addEventListener('load', function(){ layoutNodes(); updateProgress(); });
  layoutNodes();
  updateProgress();
})();
