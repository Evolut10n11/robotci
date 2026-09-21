(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const o of document.querySelectorAll('link[rel="modulepreload"]'))n(o);new MutationObserver(o=>{for(const r of o)if(r.type==="childList")for(const l of r.addedNodes)l.tagName==="LINK"&&l.rel==="modulepreload"&&n(l)}).observe(document,{childList:!0,subtree:!0});function i(o){const r={};return o.integrity&&(r.integrity=o.integrity),o.referrerPolicy&&(r.referrerPolicy=o.referrerPolicy),o.crossOrigin==="use-credentials"?r.credentials="include":o.crossOrigin==="anonymous"?r.credentials="omit":r.credentials="same-origin",r}function n(o){if(o.ep)return;o.ep=!0;const r=i(o);fetch(o.href,r)}})();const oe="modulepreload",re=function(e,t){return new URL(e,t).href},G={},le=function(t,i,n){let o=Promise.resolve();if(i&&i.length>0){let y=function(p){return Promise.all(p.map(g=>Promise.resolve(g).then($=>({status:"fulfilled",value:$}),$=>({status:"rejected",reason:$}))))};const l=document.getElementsByTagName("link"),d=document.querySelector("meta[property=csp-nonce]"),h=d?.nonce||d?.getAttribute("nonce");o=y(i.map(p=>{if(p=re(p,n),p in G)return;G[p]=!0;const g=p.endsWith(".css"),$=g?'[rel="stylesheet"]':"";if(!!n)for(let c=l.length-1;c>=0;c--){const m=l[c];if(m.href===p&&(!g||m.rel==="stylesheet"))return}else if(document.querySelector(`link[href="${p}"]${$}`))return;const w=document.createElement("link");if(w.rel=g?"stylesheet":oe,g||(w.as="script"),w.crossOrigin="",w.href=p,h&&w.setAttribute("nonce",h),document.head.appendChild(w),g)return new Promise((c,m)=>{w.addEventListener("load",c),w.addEventListener("error",()=>m(new Error(`Unable to preload CSS for ${p}`)))})}))}function r(l){const d=new Event("vite:preloadError",{cancelable:!0});if(d.payload=l,window.dispatchEvent(d),!d.defaultPrevented)throw l}return o.then(l=>{for(const d of l||[])d.status==="rejected"&&r(d.reason);return t().catch(r)})},de=`<!-- Integrated from the approved 12ui Replay, Compare and Open recordings designs. -->
<div class="workbench">
  <aside class="sidebar" id="sidebar">
    <a aria-label="RobotCI Replay" class="brand" href="#replay"
      ><svg
        fill="none"
        height="100%"
        preserveaspectratio="xMidYMid meet"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        viewbox="0 0 24 24"
        width="100%"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M21 16.008v-8.018a1.98 1.98 0 0 0 -1 -1.717l-7 -4.008a2.016 2.016 0 0 0 -2 0l-7 4.008c-.619 .355 -1 1.01 -1 1.718v8.018c0 .709 .381 1.363 1 1.717l7 4.008a2.016 2.016 0 0 0 2 0l7 -4.008c.619 -.355 1 -1.01 1 -1.718"
        ></path>
        <path d="M12 22v-10"></path>
        <path d="M12 12l8.73 -5.04"></path>
        <path d="M3.27 6.96l8.73 5.04"></path></svg
      ><span>RobotCI</span></a
    >
    <div class="workspace-label">REPLAY WORKSPACE</div>
    <nav aria-label="Workspace">
      <button class="nav-button" data-mode="replay">
        <span aria-hidden="true">▷</span>Replay</button
      ><button class="nav-button" data-mode="compare">
        <span aria-hidden="true">⇄</span>Compare
      </button>
    </nav>
    <div class="section-label">SCENARIOS <span id="scenario-count"></span></div>
    <div aria-label="Scenarios" class="scenario-list" id="scenario-list"></div>
    <div class="sidebar-bottom">
      <div class="workspace-status">
        <span class="status-dot"></span>Local workspace
        <p>Recorded evidence. On your machine.</p>
      </div>
      <button class="help-button" id="help-button">
        Keyboard shortcuts <kbd>?</kbd>
      </button>
    </div>
  </aside>
  <main id="main-content">
    <header class="workspace-header" id="workspace-header">
      <div class="heading">
        <div class="heading-line">
          <h1 id="scenario-title">Replay workspace</h1>
          <span class="badge" id="source-badge">Loading</span>
        </div>
        <p id="workspace-subtitle">Inspect recorded robot behavior.</p>
      </div>
      <div class="header-actions">
        <button class="button" id="open-button">
          <span aria-hidden="true">↥</span> Open recordings</button
        ><a
          class="button"
          aria-disabled="true"
          tabindex="-1"
          id="export-button"
        >
          <span aria-hidden="true">↓</span> Export JSON
        </a>
      </div>
    </header>
    <div class="notice" hidden="" id="app-alert" role="status"></div>
    <div class="source-summary" id="source-summary"></div>
    <div class="analysis-grid" id="analysis-grid">
      <section aria-label="Trajectory replay" class="replay-column">
        <div class="panel trajectory" id="trajectory">
          <div class="plot-toolbar">
            <div aria-label="View" class="segmented" role="group">
              <button aria-pressed="true" id="top-button">Top view</button
              ><button aria-pressed="false" id="scene-button">3D</button>
            </div>
            <button
              class="button small"
              id="fit-button"
              title="Fit trajectories (F)"
            >
              Fit</button
            ><span class="frame-label" id="frame-label"></span>
          </div>
          <div class="viewport" id="viewport"></div>
          <div class="plot-empty" hidden="" id="plot-empty"></div>
          <div class="plot-legend" id="legend"></div>
          <div class="axis-note">x / y · metres</div>
          <span class="view-hint" id="view-hint"
            >Drag to pan · scroll to zoom</span
          >
        </div>
        <div class="panel playback" id="playback">
          <button
            aria-label="Play"
            class="play-button"
            disabled=""
            id="play-button"
            title="Play / pause (Space)"
          >
            ▶</button
          ><button
            aria-label="Previous event"
            class="icon-button"
            disabled=""
            id="previous-event"
            title="Previous event ([)"
          >
            Ⅰ◀</button
          ><button
            aria-label="Next event"
            class="icon-button"
            disabled=""
            id="next-event"
            title="Next event (])"
          >
            ▶Ⅰ</button
          ><output class="time-display" id="time-display">0.00 / 0.00 s</output
          ><input
            aria-label="Replay time"
            disabled=""
            id="seek"
            max="1"
            min="0"
            step="0.01"
            type="range"
            value="0"
          /><label class="speed-label"
            ><span class="sr-only">Playback speed</span
            ><select id="speed">
              <option value="0.25">0.25×</option>
              <option value="0.5">0.5×</option>
              <option selected="" value="1">1×</option>
              <option value="2">2×</option>
              <option value="4">4×</option>
            </select></label
          ><label class="loop-label"
            ><input id="loop" type="checkbox" />Loop</label
          >
        </div>
        <div class="panel timeline" id="timeline">
          <div id="event-tracks"></div>
          <div class="timeline-footer">
            <span>Recorded events</span
            ><span id="sync-note">Elapsed time · seconds</span>
          </div>
        </div>
      </section>
      <aside class="panel inspector" id="inspector">
        <div class="panel-heading">
          <h2>Run inspector</h2>
          <span class="badge" id="run-status"></span>
        </div>
        <div id="recorded-metrics"></div>
        <section class="live-section">
          <div class="section-heading">
            <h3>Pose at playhead</h3>
            <span class="mono" id="pose-time"></span>
          </div>
          <div class="live-pose" id="live-pose"></div>
          <p class="microcopy" id="sample-note"></p>
        </section>
        <section class="gate-panel" id="gate-panel"></section>
      </aside>
    </div>
    <div class="evidence-grid">
      <section class="panel evidence" id="evidence">
        <div class="panel-heading">
          <h2 id="evidence-title">Recorded metrics</h2>
          <span class="microcopy" id="evidence-badge"></span>
        </div>
        <div class="table-scroll">
          <table>
            <thead id="metrics-head"></thead>
            <tbody id="metrics-body"></tbody>
          </table>
        </div>
        <p class="panel-footnote" id="metrics-note"></p>
      </section>
      <section class="panel event-log" id="event-log">
        <div class="panel-heading">
          <h2>Event log</h2>
          <span class="microcopy" id="event-count"></span>
        </div>
        <div class="event-list" id="event-list"></div>
      </section>
    </div>
    <footer class="app-footer">
      <span>RobotCI · Replay v1</span
      ><span id="session-footnote">Read-only analysis</span>
    </footer>
  </main>
  <dialog aria-labelledby="open-title" id="open-dialog">
    <form id="open-form">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">LOCAL EVIDENCE</p>
          <h2 id="open-title">Open recordings</h2>
        </div>
        <button
          aria-label="Close recordings dialog"
          class="icon-button"
          data-close="open-dialog"
          type="button"
        >
          ×
        </button>
      </div>
      <p class="dialog-intro">
        Load Replay v1 files to inspect a run or compare two trajectories.
      </p>
      <label class="file-field"
        ><span>Candidate recording <small>Required</small></span
        ><input
          accept=".json,application/json"
          id="candidate-file"
          required=""
          type="file"
        /><span class="file-hint"
          >Choose a .replay.json file · up to 32 MiB</span
        ></label
      ><label class="file-field"
        ><span>Baseline recording <small>Optional</small></span
        ><input
          accept=".json,application/json"
          id="baseline-file"
          type="file"
        /><span class="file-hint"
          >Add a baseline for synchronized visual comparison.</span
        ></label
      >
      <p class="notice error" hidden="" id="import-error" role="alert"></p>
      <div class="privacy-note">
        <strong>Your recordings stay with you.</strong>
        <p>
          Files are read in this browser and are never uploaded. Replay files
          enable visual comparison; an official gate requires suite results
          opened from the CLI.
        </p>
      </div>
      <div class="dialog-actions">
        <button class="button" data-close="open-dialog" type="button">
          Cancel</button
        ><button class="button primary" id="import-button" type="submit">
          Open workspace
        </button>
      </div>
    </form>
  </dialog>
  <dialog aria-labelledby="help-title" id="help-dialog">
    <div class="dialog-heading">
      <h2 id="help-title">Keyboard shortcuts</h2>
      <button
        aria-label="Close shortcuts"
        class="icon-button"
        data-close="help-dialog"
      >
        ×
      </button>
    </div>
    <dl class="shortcuts">
      <div>
        <dt>Play / pause</dt>
        <dd><kbd>Space</kbd></dd>
      </div>
      <div>
        <dt>Seek one second</dt>
        <dd><kbd>←</kbd> <kbd>→</kbd></dd>
      </div>
      <div>
        <dt>Previous / next event</dt>
        <dd><kbd>[</kbd> <kbd>]</kbd></dd>
      </div>
      <div>
        <dt>Start / end</dt>
        <dd><kbd>Home</kbd> <kbd>End</kbd></dd>
      </div>
      <div>
        <dt>Fit trajectories</dt>
        <dd><kbd>F</kbd></dd>
      </div>
      <div>
        <dt>Open recordings</dt>
        <dd><kbd>O</kbd></dd>
      </div>
    </dl>
    <p class="microcopy">Shortcuts are paused while you use form controls.</p>
  </dialog>
</div>
`,ce=(e,t,i)=>Math.min(i,Math.max(t,e)),U=(e,t,i)=>e+(t-e)*i;function pe(e,t,i){const n=Math.atan2(Math.sin(t-e),Math.cos(t-e));return e+n*i}function z(e,t){if(t<=e[0].t)return e[0];const i=e[e.length-1];if(t>=i.t)return i;let n=1,o=e.length-1;for(;n<o;){const g=Math.floor((n+o)/2);e[g].t<t?n=g+1:o=g}const r=n,l=r-1,d=e[l],h=e[r],y=Math.max(1e-4,h.t-d.t),p=ce((t-d.t)/y,0,1);return{t,position:{x:U(d.position.x,h.position.x,p),y:U(d.position.y,h.position.y,p),z:U(d.position.z,h.position.z,p)},orientation:{yaw:pe(d.orientation.yaw,h.orientation.yaw,p)}}}const Z=32*1024*1024,ue=25e4,A=[{key:"duration_sec",label:"Duration",unit:"s",policy:"max_duration_increase_pct",deltaUnit:"%"},{key:"path_length_m",label:"Path length",unit:"m",policy:"max_path_length_increase_pct",deltaUnit:"%"},{key:"distance_to_goal_m",label:"Final distance to goal",unit:"m",policy:"max_distance_to_goal_increase_m",deltaUnit:"m"},{key:"stuck_events",label:"Stuck events",unit:"",policy:"max_stuck_events_increase",deltaUnit:""},{key:"recoveries",label:"Recoveries",unit:"",policy:"max_recoveries_increase",deltaUnit:""}],u=e=>{throw new Error(e)},k=(e,t)=>e&&typeof e=="object"&&!Array.isArray(e)?e:u(`${t} must be an object.`),E=(e,t)=>typeof e=="number"&&Number.isFinite(e)?e:u(`${t} must be a finite number.`),_=(e,t)=>typeof e=="string"&&e.trim()?e:u(`${t} must be a non-empty string.`),K=(e,t)=>{k(e,t);for(const i of["x","y","z"])E(e[i],`${t}.${i}`)},Q=(e,t,i=1e-6)=>Math.abs(e-t)<=i;function O(e){k(e,"Replay"),e.schema_version!==1&&u("Only Replay v1 JSON is supported."),_(e.scenario,"Scenario"),["PASS","FAIL"].includes(e.status)||u("Replay status must be PASS or FAIL.");const t=Object.hasOwn(e,"result_status")?e.result_status:e.status;["PASS","FAIL","TIMEOUT","INFRA_ERROR"].includes(t)||u("Unsupported result status."),e.status!==(t==="PASS"?"PASS":"FAIL")&&u("Replay and result statuses disagree."),_(e.runtime,"Runtime"),E(e.duration_sec,"Duration")<=0&&u("Duration must be greater than zero."),_(k(e.robot,"Robot").type,"Robot type"),_(k(e.world,"World").frame,"Coordinate frame"),K(e.world.goal,"Goal"),(!Array.isArray(e.samples)||e.samples.length<2)&&u("At least two pose samples are required."),e.samples.length>ue&&u("Recording exceeds 250,000 samples.");let i=-1/0;e.samples.forEach((n,o)=>{k(n,`Sample ${o}`),E(n.t,"Sample timestamp"),(n.t<0||n.t<i||n.t>e.duration_sec)&&u("Sample timestamps must be ordered and within the recording."),i=n.t,K(n.position,`Sample ${o}`),E(k(n.orientation,"Orientation").yaw,"Yaw")}),k(e.metrics,"Metrics");for(const{key:n}of A){const o=E(e.metrics[n],n);o<0&&u(`${n} must be non-negative.`),["stuck_events","recoveries"].includes(n)&&!Number.isInteger(o)&&u(`${n} must be an integer.`)}return Q(e.metrics.duration_sec,e.duration_sec,Math.max(.002,e.duration_sec*1e-6))||u("Duration and metrics disagree."),Array.isArray(e.events)||u("Events must be an array."),e.events.forEach(n=>{k(n,"Event"),E(n.t,"Event timestamp"),(n.t<0||n.t>e.duration_sec)&&u("Event timestamp is outside the recording."),["START","REPLAN","STUCK","RECOVERY","GOAL","FAIL"].includes(n.type)||u("Unsupported event type."),n.message!=null&&typeof n.message!="string"&&u("Event message must be text.")}),e}function me(e){new TextEncoder().encode(e).length>Z&&u("Recording exceeds the 32 MiB size limit.");let t;try{t=JSON.parse(e,(n,o)=>(typeof o=="number"&&!Number.isFinite(o)&&u("JSON contains a non-finite number."),o))}catch(n){u(`Cannot read JSON: ${n.message}`)}const i=[];for(const n of e.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)){const o=n[0],r=i.at(-1);if(o==="{")i.push({keys:new Set,key:!0});else if(o==="[")i.push({});else if(o==="}"||o==="]")i.pop();else if(o===","&&r?.keys)r.key=!0;else if(o===":"&&r?.keys)r.key=!1;else if(o.startsWith('"')&&r?.key){const l=JSON.parse(o);r.keys.has(l)&&u(`Duplicate JSON key: ${l}`),r.keys.add(l)}}return O(t)}function he(e,t){if(!e||!t)return null;if(e.scenario!==t.scenario)return"The recordings describe different scenarios.";if(e.world.frame!==t.world.frame)return"The recordings use different coordinate frames.";for(const[i,n,o]of[["start",e.samples[0].position,t.samples[0].position],["goal",e.world.goal,t.world.goal]])if(["x","y","z"].some(r=>!Q(n[r],o[r])))return`The recordings have different ${i} positions.`;return null}function fe(e,t,i,n){O(e),t&&O(t);const o=(r,l)=>({label:l,replay:r,status:r.result_status??r.status,runtime:r.runtime,metrics:r.metrics,replay_notice:null});return{schema_version:1,source:"replay",selected_scenario:e.scenario,candidate_label:i,baseline_label:t?n:null,gate:null,gate_notice:"Replay files show recorded behavior. A verified gate requires suite results.",scenarios:[{name:e.scenario,candidate:o(e,i),baseline:t?o(t,n):null,alignment_notice:he(e,t),comparison:null}]}}function be(e,t,i){return!Number.isFinite(e)||!Number.isFinite(t)?null:i!=="%"?t-e:e===0?t===0?0:1/0:(t-e)/e*100}const S=(e,t=2)=>Number.isFinite(e)?e.toLocaleString("en-US",{maximumFractionDigits:t}):"—";function D(e,t=""){return e===null?"—":Number.isFinite(e)?`${e>0?"+":""}${S(e)}${t?` ${t}`:""}`:"Unbounded"}function ve(e,t){const i=[];for(const n of t?["baseline","candidate"]:["candidate"])for(const o of e[n]?.replay?.events??[])i.push({...o,source:n});return i.sort((n,o)=>n.t-o.t||n.source.localeCompare(o.source))}function ge(e){let t=1/0,i=-1/0,n=1/0,o=-1/0;for(const l of e.filter(Boolean)){for(const{position:h}of l.samples)t=Math.min(t,h.x),i=Math.max(i,h.x),n=Math.min(n,h.y),o=Math.max(o,h.y);const d=l.world.goal;t=Math.min(t,d.x),i=Math.max(i,d.x),n=Math.min(n,d.y),o=Math.max(o,d.y)}if(!Number.isFinite(t))return{minX:-1,maxX:1,minY:-1,maxY:1};const r=Math.max(.5,Math.max(i-t,o-n)*.16);return{minX:t-r,maxX:i+r,minY:n-r,maxY:o+r}}function ye(e,t=6e3){if(e.length<=t)return e;const i=Math.ceil((e.length-1)/(t-1));return e.filter((n,o)=>o%i===0||o===e.length-1)}const xe="http://www.w3.org/2000/svg",b=(e,t={},i)=>{const n=document.createElementNS(xe,e);for(const[o,r]of Object.entries(t))n.setAttribute(o,r);return i!=null&&(n.textContent=i),n},we={candidate:"#bd602d",baseline:"#287c79"};class W{constructor(t,i){this.host=t,this.recordings=Object.entries(i).filter(([,n])=>n),this.bounds=ge(this.recordings.map(([,n])=>n)),this.svg=b("svg",{role:"img","aria-label":"Recorded trajectories in world coordinates. Drag to pan; scroll to zoom.",class:"trajectory-svg"}),t.append(this.svg),this.time=0,this.zoom=1,this.pan={x:0,y:0},this.drag=null,this.svg.addEventListener("pointerdown",n=>{n.button===0&&(this.drag={x:n.clientX,y:n.clientY,pan:{...this.pan}},this.svg.setPointerCapture(n.pointerId))}),this.svg.addEventListener("pointermove",n=>{this.drag&&(this.pan.x=this.drag.pan.x+n.clientX-this.drag.x,this.pan.y=this.drag.pan.y+n.clientY-this.drag.y,this.draw())}),this.svg.addEventListener("pointerup",()=>{this.drag=null}),this.svg.addEventListener("pointercancel",()=>{this.drag=null}),this.svg.addEventListener("wheel",n=>{n.preventDefault();const o=Math.exp(-n.deltaY*.0015);this.zoom=Math.max(.2,Math.min(20,this.zoom*o)),this.draw()},{passive:!1}),this.observer=new ResizeObserver(()=>this.draw()),this.observer.observe(t),this.draw()}fit(){this.zoom=1,this.pan={x:0,y:0},this.draw()}draw(){const t=Math.max(100,this.host.clientWidth),i=Math.max(100,this.host.clientHeight);this.svg.setAttribute("viewBox",`0 0 ${t} ${i}`);const n=this.bounds,o=Math.min((t-60)/(n.maxX-n.minX),(i-45)/(n.maxY-n.minY))*this.zoom,r=(n.minX+n.maxX)/2,l=(n.minY+n.maxY)/2;this.xy=c=>[t/2+(c.x-r)*o+this.pan.x,i/2-(c.y-l)*o+this.pan.y],this.svg.replaceChildren();const d=b("g",{class:"plot-grid"}),h=60/o,y=10**Math.floor(Math.log10(h)),p=[1,2,5,10].find(c=>c*y>=h)*y,g=r-(t/2+this.pan.x)/o,$=g+t/o,T=l+(i/2+this.pan.y)/o,w=T-i/o;for(let c=Math.ceil(g/p)*p;c<$;c+=p){const[m]=this.xy({x:c,y:0});d.append(b("line",{x1:m,x2:m,y1:0,y2:i})),d.append(b("text",{x:m+5,y:i-12},S(Math.abs(c)<p*1e-9?0:c)))}for(let c=Math.ceil(w/p)*p;c<T;c+=p){const[,m]=this.xy({x:0,y:c});d.append(b("line",{x1:0,x2:t,y1:m,y2:m})),m<i-28&&d.append(b("text",{x:12,y:m-5},S(Math.abs(c)<p*1e-9?0:c)))}this.svg.append(d),this.robots=[];for(const[c,m]of this.recordings){const L=we[c],se=ye(m.samples).map(({position:R})=>this.xy(R).join(",")).join(" ");if(this.svg.append(b("polyline",{points:se,fill:"none",stroke:L,"stroke-width":c==="candidate"?3:2.5,"stroke-dasharray":c==="baseline"?"7 5":"none","stroke-linecap":"round","stroke-linejoin":"round",opacity:.83})),c==="candidate"){const[R,X]=this.xy(m.samples[0].position),[N,P]=this.xy(m.world.goal);this.svg.append(b("circle",{cx:R,cy:X,r:5,fill:"#fff",stroke:"#4c5554","stroke-width":2})),this.svg.append(b("text",{x:R-9,y:X+24,class:"plot-label"},"Start")),this.svg.append(b("circle",{cx:N,cy:P,r:13,fill:"none",stroke:"#567a55","stroke-width":1.5,"stroke-dasharray":"3 3"})),this.svg.append(b("circle",{cx:N,cy:P,r:5,fill:"#567a55"})),this.svg.append(b("text",{x:N+20,y:P+4,class:"plot-label"},"Goal"));for(const I of m.events.filter(F=>!["START","GOAL"].includes(F.type))){const[F,ae]=this.xy(z(m.samples,I.t).position),J=b("circle",{cx:F,cy:ae,r:5,fill:"#fff9ed",stroke:L,"stroke-width":2});J.append(b("title",{},`${I.type} · ${I.t}s`)),this.svg.append(J)}}const M=b("g");M.append(b("circle",{r:13,fill:L,opacity:.13})),M.append(b("path",{d:"M 10 0 L -6 -6 L -3 0 L -6 6 Z",fill:L,stroke:"white","stroke-width":1.5})),this.svg.append(M),this.robots.push({replay:m,marker:M})}this.setTime(this.time)}setTime(t){this.time=t;for(const{replay:i,marker:n}of this.robots??[]){const o=z(i.samples,t),[r,l]=this.xy(o.position);n.setAttribute("transform",`translate(${r} ${l}) rotate(${-o.orientation.yaw*180/Math.PI})`)}}dispose(){this.observer.disconnect(),this.svg.remove()}}document.querySelector("#root").innerHTML=de;const a=e=>document.getElementById(e),f=e=>String(e??"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t]),C=(e,t="")=>`<span class="badge ${f(t)}">${f(e)}</span>`,s={session:null,scenario:null,mode:location.hash==="#compare"?"compare":"replay",view:"top",time:0,duration:0,playing:!1,speed:1,loop:!1,events:[],renderer:null,renderVersion:0,frame:null,lastTick:null};function Y(e,t=!1){a("app-alert").textContent=e||"",a("app-alert").hidden=!e,a("app-alert").classList.toggle("error",t)}function v(){s.playing=!1,cancelAnimationFrame(s.frame),s.frame=null,s.lastTick=null,a("play-button").textContent="▶",a("play-button").setAttribute("aria-label","Play")}function B(){const e=s.scenario;return{candidate:e?.candidate.replay,baseline:s.mode==="compare"&&!e?.alignment_notice?e?.baseline?.replay:null}}function x(e){s.time=Math.max(0,Math.min(s.duration,e)),a("seek").value=s.time,a("seek").setAttribute("aria-valuetext",`${s.time.toFixed(2)} of ${s.duration.toFixed(2)} seconds`),a("time-display").textContent=`${s.time.toFixed(2)} / ${s.duration.toFixed(2)} s`,a("pose-time").textContent=`${s.time.toFixed(2)} s`,s.renderer?.setTime(s.time);const t=s.scenario?.candidate.replay;if(t){const i=z(t.samples,s.time);a("live-pose").innerHTML=[["x",i.position.x,"m"],["y",i.position.y,"m"],["z",i.position.z,"m"],["yaw",i.orientation.yaw*180/Math.PI,"°"]].map(([n,o,r])=>`<div class="pose-cell">${n}<strong>${f(S(o,3))} ${r}</strong></div>`).join(""),a("sample-note").textContent=`${t.samples.length.toLocaleString()} recorded samples · ${s.time>t.samples.at(-1).t?"holding final recorded pose":"interpolated pose"}`}else a("live-pose").textContent="No recorded pose",a("sample-note").textContent="Result metrics remain available below.";document.querySelectorAll(".track-cursor").forEach(i=>{i.style.left=`${s.duration?s.time/s.duration*100:0}%`}),a("previous-event").disabled=!s.events.some(i=>i.t<s.time-.001),a("next-event").disabled=!s.events.some(i=>i.t>s.time+.001)}function ee(e){if(s.playing){if(s.lastTick!==null){const t=s.time+Math.min((e-s.lastTick)/1e3,.25)*s.speed;if(t>=s.duration&&!s.loop){x(s.duration),v();return}x(s.loop?t%s.duration:t)}s.lastTick=e,s.frame=requestAnimationFrame(ee)}}function te(){if(s.duration){if(s.playing){v();return}s.time>=s.duration&&x(0),s.playing=!0,s.lastTick=null,a("play-button").textContent="Ⅱ",a("play-button").setAttribute("aria-label","Pause"),s.frame=requestAnimationFrame(ee)}}function j(e){const t=e>0?s.events.find(i=>i.t>s.time+.001):s.events.findLast(i=>i.t<s.time-.001);t&&(v(),x(t.t))}function ne(e){s.mode=e,history.replaceState(null,"",`#${e}`),s.scenario&&H()}function ke(){const e=s.session,t=s.scenario,i=e.source==="demo"||t.candidate.replay?.runtime==="deterministic_demo";a("source-summary").innerHTML=["baseline","candidate"].filter(n=>t[n]).map(n=>`<div class="source-item"><span class="source-dot ${n}"></span><span>${n==="candidate"?"Candidate":"Baseline"}</span><span class="source-name" title="${f(t[n].label)}">${f(t[n].label)}</span>${C(t[n].status,t[n].status==="PASS"?"pass":"fail")}</div>`).join(""),a("scenario-title").textContent=t.name,document.title=`RobotCI · ${t.name}`,a("workspace-subtitle").textContent=s.mode==="compare"?"Baseline and candidate. One timeline, recorded evidence.":"Inspect the trajectory. Understand what happened.",a("source-badge").textContent=i?"Synthetic demo":e.gate?"Suite evidence":e.source==="suite"?"Suite results":"Replay v1",a("source-badge").className=`badge${i?" demo":""}`,a("scenario-count").textContent=e.scenarios.length,a("scenario-list").innerHTML=e.scenarios.map((n,o)=>`<button class="scenario-button" data-scenario="${o}" aria-current="${n.name===t.name}"><span class="scenario-dot ${n.comparison?.status==="REGRESSION"?"regression":""}"></span><span class="scenario-name">${f(n.name)}</span></button>`).join(""),document.querySelectorAll("[data-mode]").forEach(n=>n.setAttribute("aria-current",n.dataset.mode===s.mode?"page":"false")),Le(),a("export-button").textContent=e.gate?"↓ Export gate JSON":"↓ Export replay",a("session-footnote").textContent=i?"Synthetic data · no gate verdict":e.gate?"Gate evaluated by the RobotCI regression engine":"Read-only analysis · no gate verdict"}function $e(){const e=s.scenario;a("run-status").textContent=`Run ${e.candidate.status}`,a("run-status").className=`badge ${e.candidate.status==="PASS"?"pass":"fail"}`,a("recorded-metrics").innerHTML=`<dl class="metric-list">${A.map(i=>`<div><dt>${f(i.label)}</dt><dd>${f(S(e.candidate.metrics[i.key]))}${Number.isFinite(e.candidate.metrics[i.key])&&i.unit?` ${i.unit}`:""}</dd></div>`).join("")}</dl>`;const t=s.session.gate;if(t){const i=e.comparison?.findings??[];a("gate-panel").innerHTML=`<div class="gate-title"><h3>Official suite gate</h3>${C(t.status,t.status.toLowerCase())}</div><p>Compared suite results with matching task and execution evidence.</p><div class="gate-summary ${t.status==="REGRESSION"?"regression":""}">${C(e.comparison?.status??"Unavailable",e.comparison?.status?.toLowerCase())} <span>This scenario · ${i.length} finding${i.length===1?"":"s"}</span></div>${i.length?`<ul class="finding-list">${i.map(n=>`<li><span>${f(A.find(o=>o.key===n.metric)?.label??n.metric)}</span><strong>${f(D(n.increase_unbounded?1/0:n.increase,n.unit))}</strong></li>`).join("")}</ul>`:""}<p>Policy limits are shown below. Export the gate report for full precision.</p>`}else a("gate-panel").innerHTML=`<div class="gate-title"><h3>${e.baseline?"Visual comparison":"Recorded evidence"}</h3>${C("No gate verdict")}</div><p>${f(s.session.gate_notice)}</p>${e.baseline?"":'<button id="add-baseline" class="button">Open recordings to compare</button>'}`,a("add-baseline")?.addEventListener("click",V)}function Ee(){const e=s.scenario,t=!!e.baseline,i=s.session.gate&&e.comparison;a("evidence-title").textContent=t?"Metric comparison":"Recorded metrics",a("evidence-badge").textContent=i?"Policy evaluated":t?"Visual comparison":"Final run values",a("metrics-head").innerHTML=`<tr><th scope="col">Metric</th>${t?'<th scope="col">Baseline</th>':""}<th scope="col">Candidate</th>${t?'<th scope="col">Change</th>':""}${i?'<th scope="col">Limit</th><th scope="col">Gate</th>':""}</tr>`,a("metrics-body").innerHTML=A.map(n=>{const o=e.baseline?.metrics[n.key],r=e.candidate.metrics[n.key],l=e.alignment_notice?null:be(o,r,n.deltaUnit),d=e.comparison?.findings.find(y=>y.metric===n.key),h=y=>`${S(y,6)}${Number.isFinite(y)&&n.unit?` ${n.unit}`:""}`;return`<tr class="${d?"metric-finding":""}"><td>${n.label}</td>${t?`<td title="${f(o)}">${h(o)}</td>`:""}<td title="${f(r)}">${h(r)}</td>${t?`<td class="${l>0?"increase":l<0?"decrease":""}">${D(l,n.deltaUnit)}</td>`:""}${i?`<td>≤ ${D(s.session.gate.policy[n.policy],n.deltaUnit)}</td><td>${d?"Exceeded":"Within limit"}</td>`:""}</tr>`}).join(""),a("metrics-note").textContent=e.alignment_notice?"Deltas are hidden because these recordings do not align.":t?`Changes are candidate − baseline. Duration and path use percent; other metrics use absolute units.${i?"":" These differences are not a gate verdict."}`:"Final values from the recording or scenario result; they do not change with the playhead."}function Se(){s.events=ve(s.scenario,s.mode==="compare"&&!s.scenario.alignment_notice);const e=s.events.slice(0,1e3);a("event-count").textContent=`${s.events.length} recorded${s.events.length>1e3?" · first 1,000 shown":""}`,a("event-list").innerHTML=e.length?e.map((i,n)=>`<button class="event-row" data-event="${n}" title="Seek to ${i.t} seconds"><time>${i.t.toFixed(2)} s</time><span><span class="event-description"><span class="source-dot ${i.source}"></span>${f(i.type)} <span class="microcopy">${i.source}</span></span><small>${f(i.message??"Recorded event")}</small></span></button>`).join(""):'<p class="microcopy">No timestamped events were recorded. Event counts may still be present in the result metrics.</p>';const t=Object.entries(B()).filter(([,i])=>i);a("event-tracks").innerHTML=t.map(([i])=>`<div class="event-track"><span>${i==="baseline"?"Baseline":"Candidate"}</span><div class="track-rail">${e.map((n,o)=>n.source===i?`<button class="track-event ${i}" data-event="${o}" style="left:${s.duration?n.t/s.duration*100:0}%" aria-label="${f(`${i} ${n.type} at ${n.t} seconds`)}" title="${f(`${n.type} · ${n.t}s`)}">◆</button>`:"").join("")}<span class="track-cursor"></span></div></div>`).join("")||'<span class="microcopy">A recorded trajectory is required for playback.</span>',a("sync-note").textContent=t.length>1?"Synced by elapsed time · final pose held":"Elapsed time · seconds"}async function q(){const e=++s.renderVersion;s.renderer?.dispose(),s.renderer=null,a("viewport").replaceChildren();const t=B(),i=Object.values(t).some(Boolean);if(a("plot-empty").hidden=i,a("fit-button").disabled=!i,a("scene-button").disabled=!i,a("top-button").setAttribute("aria-pressed",s.view==="top"),a("scene-button").setAttribute("aria-pressed",s.view==="3d"),a("frame-label").textContent=(t.candidate??t.baseline)?.world.frame?`frame: ${(t.candidate??t.baseline).world.frame}`:"",a("legend").innerHTML=Object.keys(t).filter(n=>t[n]).map(n=>`<span class="legend-item"><span class="legend-line ${n}"></span>${n==="candidate"?"Candidate":"Baseline"}</span>`).join(""),a("legend").hidden=!i,!i){a("plot-empty").innerHTML=`<strong>No trajectory available</strong><p>${f(s.scenario.candidate.replay_notice??"Open a Replay v1 recording to inspect the trajectory.")}</p>`;return}try{if(s.view==="3d"){const{SceneView:n}=await le(async()=>{const{SceneView:o}=await import("./scene-view-CZfFiT4e.js");return{SceneView:o}},[],import.meta.url);if(e!==s.renderVersion)return;s.renderer=new n(a("viewport"),t)}else s.renderer=new W(a("viewport"),t)}catch{if(e!==s.renderVersion)return;s.view="top",a("viewport").replaceChildren(),s.renderer=new W(a("viewport"),t),a("top-button").setAttribute("aria-pressed","true"),a("scene-button").setAttribute("aria-pressed","false"),Y("3D is unavailable in this browser. The top view still shows the full recorded trajectory.",!0)}a("view-hint").textContent=s.view==="3d"?"Drag to orbit · scroll to zoom":"Drag to pan · scroll to zoom",s.renderer?.setTime(s.time)}function H(){v();const e=B();s.duration=Math.max(0,...Object.values(e).filter(Boolean).map(i=>i.duration_sec)),s.time=0,a("seek").max=s.duration||1,a("seek").disabled=!s.duration,a("play-button").disabled=!s.duration;const t=[];s.mode==="compare"&&(s.scenario.baseline||t.push("Open a baseline recording to compare runs."),s.scenario.alignment_notice&&t.push(`${s.scenario.alignment_notice} Showing the candidate trajectory only.`),s.scenario.baseline?.replay_notice&&t.push(`Baseline: ${s.scenario.baseline.replay_notice}`)),s.scenario.candidate.replay_notice&&e.baseline&&t.push(`Candidate: ${s.scenario.candidate.replay_notice}`),Y(t.join(" ")),ke(),$e(),Ee(),Se(),x(0),q()}function ie(e){if(e.schema_version!==1||!Array.isArray(e.scenarios)||!e.scenarios.length)throw new Error("Unsupported viewer session.");for(const t of e.scenarios)for(const i of["candidate","baseline"])t[i]?.replay&&O(t[i].replay);s.session=e,s.scenario=e.scenarios.find(t=>t.name===e.selected_scenario)??e.scenarios[0],H()}function V(){v(),a("import-error").hidden=!0,a("open-dialog").showModal()}function Le(){const e=a("export-button");s.exportURL&&URL.revokeObjectURL(s.exportURL),s.exportURL=null;const t=s.session.gate??s.scenario.candidate.replay;if(e.setAttribute("aria-disabled",String(!t)),!t){e.removeAttribute("href"),e.tabIndex=-1;return}e.tabIndex=0,e.download=s.session.gate?"robotci-suite-gate.json":`${s.scenario.name.replace(/[^a-zA-Z0-9_-]/g,"_")}.replay.json`,s.exportURL=URL.createObjectURL(new Blob([JSON.stringify(t,null,2)+`
`],{type:"application/json"})),e.href=s.exportURL}a("play-button").addEventListener("click",te);a("previous-event").addEventListener("click",()=>j(-1));a("next-event").addEventListener("click",()=>j(1));a("seek").addEventListener("input",e=>{v(),x(Number(e.target.value))});a("speed").addEventListener("change",e=>{s.speed=Number(e.target.value)});a("loop").addEventListener("change",e=>{s.loop=e.target.checked});a("fit-button").addEventListener("click",()=>s.renderer?.fit());a("top-button").addEventListener("click",()=>{s.view="top",q()});a("scene-button").addEventListener("click",()=>{s.view="3d",q()});a("open-button").addEventListener("click",V);a("help-button").addEventListener("click",()=>{v(),a("help-dialog").showModal()});document.querySelector(".brand").addEventListener("click",e=>{e.preventDefault(),ne("replay")});document.querySelectorAll("[data-mode]").forEach(e=>e.addEventListener("click",()=>ne(e.dataset.mode)));document.querySelectorAll("[data-close]").forEach(e=>e.addEventListener("click",()=>a(e.dataset.close).close()));a("scenario-list").addEventListener("click",e=>{const t=e.target.closest("[data-scenario]");t&&(s.scenario=s.session.scenarios[Number(t.dataset.scenario)],H())});for(const e of["event-list","event-tracks"])a(e).addEventListener("click",t=>{const i=t.target.closest("[data-event]");i&&(v(),x(s.events[Number(i.dataset.event)].t))});a("open-form").addEventListener("submit",async e=>{e.preventDefault(),a("import-error").hidden=!0,a("import-button").disabled=!0,a("import-button").textContent="Reading recordings…";try{const t=a("candidate-file").files[0],i=a("baseline-file").files[0];if(!t)throw new Error("Choose a candidate recording first.");const n=async l=>{if(l.size>Z)throw new Error(`${l.name} exceeds the 32 MiB size limit.`);try{return me(await l.text())}catch(d){throw new Error(`${l.name}: ${d.message}`)}},[o,r]=await Promise.all([n(t),i?n(i):null]);s.mode=r?"compare":"replay",history.replaceState(null,"",`#${s.mode}`),ie(fe(o,r,t.name,i?.name)),a("open-dialog").close(),a("open-form").reset()}catch(t){a("import-error").textContent=t.message,a("import-error").hidden=!1}finally{a("import-button").disabled=!1,a("import-button").textContent="Open workspace"}});document.addEventListener("keydown",e=>{if(e.ctrlKey||e.metaKey||e.altKey||document.querySelector("dialog[open]")||e.target.closest("input,select,textarea,button,a,[contenteditable]"))return;const i={" ":te,ArrowLeft:()=>{v(),x(s.time-1)},ArrowRight:()=>{v(),x(s.time+1)},Home:()=>{v(),x(0)},End:()=>{v(),x(s.duration)},"[":()=>j(-1),"]":()=>j(1),f:()=>s.renderer?.fit(),o:V,"?":()=>{v(),a("help-dialog").showModal()}}[e.key];i&&(e.preventDefault(),i())});document.addEventListener("visibilitychange",()=>{document.hidden&&v()});window.addEventListener("pagehide",()=>{v(),s.renderVersion++,s.renderer?.dispose()});async function Me(){try{const e=await fetch("/api/session",{cache:"no-store"});if(!e.ok)throw new Error(`Viewer returned HTTP ${e.status}.`);ie(await e.json())}catch(e){a("source-badge").textContent="Offline",Y(`Could not load the workspace. ${e.message} You can still open local recordings.`,!0),a("plot-empty").hidden=!1,a("plot-empty").innerHTML="<strong>Open a recording to begin</strong><p>Choose a candidate Replay v1 file, and optionally a baseline.</p>"}}Me();export{we as C,ye as d,z as s,ge as t};
