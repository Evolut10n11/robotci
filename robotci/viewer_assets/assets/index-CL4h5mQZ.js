(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const o of document.querySelectorAll('link[rel="modulepreload"]'))n(o);new MutationObserver(o=>{for(const r of o)if(r.type==="childList")for(const l of r.addedNodes)l.tagName==="LINK"&&l.rel==="modulepreload"&&n(l)}).observe(document,{childList:!0,subtree:!0});function i(o){const r={};return o.integrity&&(r.integrity=o.integrity),o.referrerPolicy&&(r.referrerPolicy=o.referrerPolicy),o.crossOrigin==="use-credentials"?r.credentials="include":o.crossOrigin==="anonymous"?r.credentials="omit":r.credentials="same-origin",r}function n(o){if(o.ep)return;o.ep=!0;const r=i(o);fetch(o.href,r)}})();const ue="modulepreload",me=function(e,t){return new URL(e,t).href},te={},he=function(t,i,n){let o=Promise.resolve();if(i&&i.length>0){let y=function(p){return Promise.all(p.map(g=>Promise.resolve(g).then(L=>({status:"fulfilled",value:L}),L=>({status:"rejected",reason:L}))))};const l=document.getElementsByTagName("link"),c=document.querySelector("meta[property=csp-nonce]"),f=c?.nonce||c?.getAttribute("nonce");o=y(i.map(p=>{if(p=me(p,n),p in te)return;te[p]=!0;const g=p.endsWith(".css"),L=g?'[rel="stylesheet"]':"";if(!!n)for(let d=l.length-1;d>=0;d--){const m=l[d];if(m.href===p&&(!g||m.rel==="stylesheet"))return}else if(document.querySelector(`link[href="${p}"]${L}`))return;const $=document.createElement("link");if($.rel=g?"stylesheet":ue,g||($.as="script"),$.crossOrigin="",$.href=p,f&&$.setAttribute("nonce",f),document.head.appendChild($),g)return new Promise((d,m)=>{$.addEventListener("load",d),$.addEventListener("error",()=>m(new Error(`Unable to preload CSS for ${p}`)))})}))}function r(l){const c=new Event("vite:preloadError",{cancelable:!0});if(c.payload=l,window.dispatchEvent(c),!c.defaultPrevented)throw l}return o.then(l=>{for(const c of l||[])c.status==="rejected"&&r(c.reason);return t().catch(r)})},M=e=>e==="baseline"?"Эталон":"Новый прогон",N=e=>({PASS:"Успешно",FAIL:"Сбой",TIMEOUT:"Таймаут",INFRA_ERROR:"Ошибка среды",REGRESSION:"Регрессия"})[e]??e,O=e=>({START:"Старт",REPLAN:"Перестроение пути",STUCK:"Застревание",RECOVERY:"Восстановление",GOAL:"Цель достигнута",FAIL:"Сбой"})[e]??e,fe=e=>({"Demo candidate":"Демонстрационный прогон","Demo baseline":"Демонстрационный эталон","Candidate recording":"Новый прогон","Baseline recording":"Эталонная запись"})[e]??e,w=e=>e.toLocaleString("ru-RU",{minimumFractionDigits:2,maximumFractionDigits:2,useGrouping:!1}),be=e=>({m:"м",s:"с"})[e]??e,B={SUCCEEDED:"Навигация успешно завершена",FAILED:"Навигация завершилась с ошибкой",CANCELED:"Навигация отменена",CANCELED_BY_TIMEOUT:"Навигация остановлена по таймауту",GOAL_REJECTED:"Цель отклонена",UNKNOWN:"Результат навигации неизвестен","Navigation started":"Навигация началась","Local planner stopped making progress":"Локальный планировщик перестал продвигаться к цели","Recovery behavior completed":"Восстановление завершено","Goal reached":"Цель достигнута","Synthetic baseline started":"Запущен демонстрационный эталон","Synthetic baseline reached the goal":"Демонстрационный эталон достиг цели","The recordings describe different scenarios.":"Записи относятся к разным сценариям.","The recordings use different coordinate frames.":"У записей разные системы координат.","The recordings have different start positions.":"У записей разные начальные положения.","The recordings have different goal positions.":"У записей разные целевые положения.","Replay files show recorded behavior. A verified gate requires suite results.":"Записи показывают поведение робота. Для проверки регрессий нужны результаты набора сценариев.","Open a baseline suite to evaluate the regression gate.":"Откройте эталонный набор результатов, чтобы проверить регрессии.","No trajectory was recorded for this result. Metrics are still available.":"Для этого результата нет записи траектории. Метрики по-прежнему доступны."},ve=e=>B[e]??e??"Записанное событие";function S(e){return e?B[e]?B[e]:e.startsWith("Gate unavailable:")?"Проверка регрессий недоступна: результаты не прошли проверку совместимости. Проверьте статусы, сценарии и параметры среды. Техническая причина доступна в подсказке.":e.startsWith("Trajectory unavailable:")?"Траектория недоступна: запись не прошла проверку или не соответствует результату. Метрики доступны. Техническая причина доступна в подсказке.":e:""}const ge=`<!-- Integrated from the approved 12ui Replay, Compare and Открыть записи designs. -->
<div class="workbench">
  <aside class="sidebar" id="sidebar">
    <a aria-label="RobotCI — просмотр записей" class="brand" href="#replay"
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
    <div class="workspace-label">ПРОСМОТР ЗАПИСЕЙ</div>
    <nav aria-label="Рабочая область">
      <button class="nav-button" data-mode="replay">
        <span aria-hidden="true">▷</span>Просмотр</button
      ><button class="nav-button" data-mode="compare">
        <span aria-hidden="true">⇄</span>Сравнение
      </button>
    </nav>
    <div class="section-label">СЦЕНАРИИ <span id="scenario-count"></span></div>
    <div aria-label="Сценарии" class="scenario-list" id="scenario-list"></div>
    <div class="sidebar-bottom">
      <div class="workspace-status">
        <span class="status-dot"></span>Локальный просмотр
        <p>Записи и результаты на вашем компьютере.</p>
      </div>
      <button class="help-button" id="help-button">
        Горячие клавиши <kbd>?</kbd>
      </button>
    </div>
  </aside>
  <main id="main-content">
    <header class="workspace-header" id="workspace-header">
      <div class="heading">
        <div class="heading-line">
          <h1 id="scenario-title">Просмотр записей</h1>
          <span class="badge" id="source-badge">Загрузка</span>
        </div>
        <p id="workspace-subtitle">Исследуйте записанное поведение робота.</p>
      </div>
      <div class="header-actions">
        <button class="button" id="open-button">
          <span aria-hidden="true">↥</span> Открыть записи</button
        ><a
          class="button"
          aria-disabled="true"
          tabindex="-1"
          id="export-button"
        >
          <span aria-hidden="true">↓</span> Скачать JSON
        </a>
      </div>
    </header>
    <div class="notice" hidden="" id="app-alert" role="status"></div>
    <div class="source-summary" id="source-summary"></div>
    <div class="analysis-grid" id="analysis-grid">
      <section aria-label="Воспроизведение траектории" class="replay-column">
        <div class="panel trajectory" id="trajectory">
          <div class="plot-toolbar">
            <div aria-label="Вид" class="segmented" role="group">
              <button aria-pressed="true" id="top-button">Вид сверху</button
              ><button aria-pressed="false" id="scene-button">3D</button>
            </div>
            <button
              class="button small"
              id="fit-button"
              title="Вписать траектории (F / А)"
            >
              Вписать</button
            ><span class="frame-label" id="frame-label"></span>
          </div>
          <div class="viewport" id="viewport"></div>
          <div class="plot-empty" hidden="" id="plot-empty"></div>
          <div class="plot-legend" id="legend"></div>
          <div class="axis-note">x / y · метры</div>
          <span class="view-hint" id="view-hint"
            >Перетаскивание — сдвиг · колесо — масштаб</span
          >
        </div>
        <div class="panel playback" id="playback">
          <button
            aria-label="Воспроизвести"
            class="play-button"
            disabled=""
            id="play-button"
            title="Воспроизведение / пауза (Пробел)"
          >
            ▶</button
          ><button
            aria-label="Предыдущее событие"
            class="icon-button"
            disabled=""
            id="previous-event"
            title="Предыдущее событие ([ / Х)"
          >
            Ⅰ◀</button
          ><button
            aria-label="Следующее событие"
            class="icon-button"
            disabled=""
            id="next-event"
            title="Следующее событие (] / Ъ)"
          >
            ▶Ⅰ</button
          ><output class="time-display" id="time-display">0,00 / 0,00 с</output
          ><input
            aria-label="Время записи"
            disabled=""
            id="seek"
            max="1"
            min="0"
            step="0.01"
            type="range"
            value="0"
          /><label class="speed-label"
            ><span class="sr-only">Скорость воспроизведения</span
            ><select id="speed">
              <option value="0.25">0,25×</option>
              <option value="0.5">0,5×</option>
              <option selected="" value="1">1×</option>
              <option value="2">2×</option>
              <option value="4">4×</option>
            </select></label
          ><label class="loop-label"
            ><input id="loop" type="checkbox" />Повтор</label
          >
        </div>
        <div class="panel timeline" id="timeline">
          <div id="event-tracks"></div>
          <div class="timeline-footer">
            <span>Записанные события</span
            ><span id="sync-note">Время от начала · секунды</span>
          </div>
        </div>
      </section>
      <aside class="panel inspector" id="inspector">
        <div class="panel-heading">
          <h2>Параметры прогона</h2>
          <span class="badge" id="run-status"></span>
        </div>
        <div id="recorded-metrics"></div>
        <section class="live-section">
          <div class="section-heading">
            <h3>Положение робота</h3>
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
          <h2 id="evidence-title">Записанные метрики</h2>
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
          <h2>Журнал событий</h2>
          <span class="microcopy" id="event-count"></span>
        </div>
        <div class="event-list" id="event-list"></div>
      </section>
    </div>
    <footer class="app-footer">
      <span>RobotCI · Replay v1</span
      ><span id="session-footnote">Просмотр без изменений</span>
    </footer>
  </main>
  <dialog aria-labelledby="open-title" id="open-dialog">
    <form id="open-form">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">ЛОКАЛЬНЫЕ ЗАПИСИ</p>
          <h2 id="open-title">Открыть записи</h2>
        </div>
        <button
          aria-label="Закрыть выбор записей"
          class="icon-button"
          data-close="open-dialog"
          type="button"
        >
          ×
        </button>
      </div>
      <p class="dialog-intro">
        Откройте файлы Replay v1 для просмотра прогона или сравнения двух траекторий.
      </p>
      <label class="file-field"
        ><span>Новый прогон <small>Обязательно</small></span
        ><input
          accept=".json,application/json"
          id="candidate-file"
          required=""
          type="file"
        /><span class="file-hint"
          >Выберите файл .replay.json · до 32 МиБ</span
        ></label
      ><label class="file-field"
        ><span>Эталонная запись <small>Необязательно</small></span
        ><input
          accept=".json,application/json"
          id="baseline-file"
          type="file"
        /><span class="file-hint"
          >Добавьте эталон для синхронного сравнения траекторий.</span
        ></label
      >
      <p class="notice error" hidden="" id="import-error" role="alert"></p>
      <div class="privacy-note">
        <strong>Записи остаются на вашем компьютере.</strong>
        <p>
          Файлы читаются в браузере и никуда не загружаются. Записи позволяют
          сравнивать траектории. Для проверки регрессий откройте результаты
          набора сценариев через команду robotci view --suite.
        </p>
      </div>
      <div class="dialog-actions">
        <button class="button" data-close="open-dialog" type="button">
          Отмена</button
        ><button class="button primary" id="import-button" type="submit">
          Открыть
        </button>
      </div>
    </form>
  </dialog>
  <dialog aria-labelledby="help-title" id="help-dialog">
    <div class="dialog-heading">
      <h2 id="help-title">Горячие клавиши</h2>
      <button
        aria-label="Закрыть горячие клавиши"
        class="icon-button"
        data-close="help-dialog"
      >
        ×
      </button>
    </div>
    <dl class="shortcuts">
      <div>
        <dt>Воспроизведение / пауза</dt>
        <dd><kbd>Пробел</kbd></dd>
      </div>
      <div>
        <dt>Перемотка на секунду</dt>
        <dd><kbd>←</kbd> <kbd>→</kbd></dd>
      </div>
      <div>
        <dt>Предыдущее / следующее событие</dt>
        <dd><kbd>[</kbd> <kbd>]</kbd></dd>
      </div>
      <div>
        <dt>Начало / конец</dt>
        <dd><kbd>Home</kbd> <kbd>End</kbd></dd>
      </div>
      <div>
        <dt>Вписать траектории</dt>
        <dd><kbd>F / А</kbd></dd>
      </div>
      <div>
        <dt>Открыть записи</dt>
        <dd><kbd>O / Щ</kbd></dd>
      </div>
    </dl>
    <p class="microcopy">Горячие клавиши не перехватываются при работе с полями формы. Поддерживаются русская и английская раскладки.</p>
  </dialog>
</div>
`,ye=(e,t,i)=>Math.min(i,Math.max(t,e)),z=(e,t,i)=>e+(t-e)*i;function xe(e,t,i){const n=Math.atan2(Math.sin(t-e),Math.cos(t-e));return e+n*i}function X(e,t){if(t<=e[0].t)return e[0];const i=e[e.length-1];if(t>=i.t)return i;let n=1,o=e.length-1;for(;n<o;){const g=Math.floor((n+o)/2);e[g].t<t?n=g+1:o=g}const r=n,l=r-1,c=e[l],f=e[r],y=Math.max(1e-4,f.t-c.t),p=ye((t-c.t)/y,0,1);return{t,position:{x:z(c.position.x,f.position.x,p),y:z(c.position.y,f.position.y,p),z:z(c.position.z,f.position.z,p)},orientation:{yaw:xe(c.orientation.yaw,f.orientation.yaw,p)}}}const se=32*1024*1024,$e=25e4,I=[{key:"duration_sec",label:"Длительность",unit:"с",policy:"max_duration_increase_pct",deltaUnit:"%"},{key:"path_length_m",label:"Длина пути",unit:"м",policy:"max_path_length_increase_pct",deltaUnit:"%"},{key:"distance_to_goal_m",label:"Расстояние до цели",unit:"м",policy:"max_distance_to_goal_increase_m",deltaUnit:"м"},{key:"stuck_events",label:"Застревания",unit:"",policy:"max_stuck_events_increase",deltaUnit:""},{key:"recoveries",label:"Восстановления",unit:"",policy:"max_recoveries_increase",deltaUnit:""}],u=e=>{throw new Error(e)},k=(e,t)=>e&&typeof e=="object"&&!Array.isArray(e)?e:u(`${t}: ожидается объект.`),_=(e,t)=>typeof e=="number"&&Number.isFinite(e)?e:u(`${t}: ожидается конечное число.`),T=(e,t)=>typeof e=="string"&&e.trim()?e:u(`${t}: ожидается непустая строка.`),ne=(e,t)=>{k(e,t);for(const i of["x","y","z"])_(e[i],`${t}.${i}`)},ae=(e,t,i=1e-6)=>Math.abs(e-t)<=i;function F(e){k(e,"Replay"),e.schema_version!==1&&u("Поддерживаются только JSON-записи Replay v1."),T(e.scenario,"Сценарий"),["PASS","FAIL"].includes(e.status)||u("Статус записи должен быть PASS или FAIL.");const t=Object.hasOwn(e,"result_status")?e.result_status:e.status;["PASS","FAIL","TIMEOUT","INFRA_ERROR"].includes(t)||u("Неподдерживаемый статус результата."),e.status!==(t==="PASS"?"PASS":"FAIL")&&u("Статусы записи и результата не совпадают."),T(e.runtime,"Среда выполнения"),_(e.duration_sec,"Длительность")<=0&&u("Длительность должна быть больше нуля."),T(k(e.robot,"Робот").type,"Тип робота"),T(k(e.world,"Мир").frame,"Система координат"),ne(e.world.goal,"Цель"),(!Array.isArray(e.samples)||e.samples.length<2)&&u("Нужно не менее двух отсчётов положения робота."),e.samples.length>$e&&u("Запись содержит больше 250 000 отсчётов.");let i=-1/0;e.samples.forEach((n,o)=>{k(n,`Отсчёт ${o}`),_(n.t,"Время отсчёта"),(n.t<0||n.t<i||n.t>e.duration_sec)&&u("Временные метки должны идти по порядку и находиться в пределах записи."),i=n.t,ne(n.position,`Отсчёт ${o}`),_(k(n.orientation,"Ориентация").yaw,"Курс")}),k(e.metrics,"Метрики");for(const{key:n}of I){const o=_(e.metrics[n],n);o<0&&u(`${n}: значение не может быть отрицательным.`),["stuck_events","recoveries"].includes(n)&&!Number.isInteger(o)&&u(`${n}: ожидается целое число.`)}return ae(e.metrics.duration_sec,e.duration_sec,Math.max(.002,e.duration_sec*1e-6))||u("Длительность записи и значение в метриках не совпадают."),Array.isArray(e.events)||u("События должны быть массивом."),e.events.forEach(n=>{k(n,"Событие"),_(n.t,"Время события"),(n.t<0||n.t>e.duration_sec)&&u("Время события находится за пределами записи."),["START","REPLAN","STUCK","RECOVERY","GOAL","FAIL"].includes(n.type)||u("Неподдерживаемый тип события."),n.message!=null&&typeof n.message!="string"&&u("Описание события должно быть текстом.")}),e}function we(e){new TextEncoder().encode(e).length>se&&u("Размер записи превышает 32 МиБ.");let t;try{t=JSON.parse(e,(n,o)=>(typeof o=="number"&&!Number.isFinite(o)&&u("JSON содержит неконечное число."),o))}catch(n){u(`Не удалось прочитать JSON: ${n instanceof SyntaxError?"проверьте синтаксис файла.":n.message}`)}const i=[];for(const n of e.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)){const o=n[0],r=i.at(-1);if(o==="{")i.push({keys:new Set,key:!0});else if(o==="[")i.push({});else if(o==="}"||o==="]")i.pop();else if(o===","&&r?.keys)r.key=!0;else if(o===":"&&r?.keys)r.key=!1;else if(o.startsWith('"')&&r?.key){const l=JSON.parse(o);r.keys.has(l)&&u(`Повторяющийся ключ JSON: ${l}`),r.keys.add(l)}}return F(t)}function ke(e,t){if(!e||!t)return null;if(e.scenario!==t.scenario)return"The recordings describe different scenarios.";if(e.world.frame!==t.world.frame)return"The recordings use different coordinate frames.";for(const[i,n,o]of[["start",e.samples[0].position,t.samples[0].position],["goal",e.world.goal,t.world.goal]])if(["x","y","z"].some(r=>!ae(n[r],o[r])))return`The recordings have different ${i} positions.`;return null}function Ee(e,t,i,n){F(e),t&&F(t);const o=(r,l)=>({label:l,replay:r,status:r.result_status??r.status,runtime:r.runtime,metrics:r.metrics,replay_notice:null});return{schema_version:1,source:"replay",selected_scenario:e.scenario,candidate_label:i,baseline_label:t?n:null,gate:null,gate_notice:"Replay files show recorded behavior. A verified gate requires suite results.",scenarios:[{name:e.scenario,candidate:o(e,i),baseline:t?o(t,n):null,alignment_notice:ke(e,t),comparison:null}]}}function Le(e,t,i){return!Number.isFinite(e)||!Number.isFinite(t)?null:i!=="%"?t-e:e===0?t===0?0:1/0:(t-e)/e*100}const E=(e,t=2)=>Number.isFinite(e)?e.toLocaleString("ru-RU",{maximumFractionDigits:t}):"—";function V(e,t=""){return e===null?"—":Number.isFinite(e)?`${e>0?"+":""}${E(e)}${t?` ${t}`:""}`:"∞"}function _e(e,t){const i=[];for(const n of t?["baseline","candidate"]:["candidate"])for(const o of e[n]?.replay?.events??[])i.push({...o,source:n});return i.sort((n,o)=>n.t-o.t||n.source.localeCompare(o.source))}function Me(e){let t=1/0,i=-1/0,n=1/0,o=-1/0;for(const l of e.filter(Boolean)){for(const{position:f}of l.samples)t=Math.min(t,f.x),i=Math.max(i,f.x),n=Math.min(n,f.y),o=Math.max(o,f.y);const c=l.world.goal;t=Math.min(t,c.x),i=Math.max(i,c.x),n=Math.min(n,c.y),o=Math.max(o,c.y)}if(!Number.isFinite(t))return{minX:-1,maxX:1,minY:-1,maxY:1};const r=Math.max(.5,Math.max(i-t,o-n)*.16);return{minX:t-r,maxX:i+r,minY:n-r,maxY:o+r}}function Se(e,t=6e3){if(e.length<=t)return e;const i=Math.ceil((e.length-1)/(t-1));return e.filter((n,o)=>o%i===0||o===e.length-1)}const Ae="http://www.w3.org/2000/svg",b=(e,t={},i)=>{const n=document.createElementNS(Ae,e);for(const[o,r]of Object.entries(t))n.setAttribute(o,r);return i!=null&&(n.textContent=i),n},Re={candidate:"#bd602d",baseline:"#287c79"};class ie{constructor(t,i){this.host=t,this.recordings=Object.entries(i).filter(([,n])=>n),this.bounds=Me(this.recordings.map(([,n])=>n)),this.svg=b("svg",{role:"img","aria-label":"Записанные траектории в системе координат мира. Перетаскивание сдвигает вид, колесо меняет масштаб.",class:"trajectory-svg"}),t.append(this.svg),this.time=0,this.zoom=1,this.pan={x:0,y:0},this.drag=null,this.svg.addEventListener("pointerdown",n=>{n.button===0&&(this.drag={x:n.clientX,y:n.clientY,pan:{...this.pan}},this.svg.setPointerCapture(n.pointerId))}),this.svg.addEventListener("pointermove",n=>{this.drag&&(this.pan.x=this.drag.pan.x+n.clientX-this.drag.x,this.pan.y=this.drag.pan.y+n.clientY-this.drag.y,this.draw())}),this.svg.addEventListener("pointerup",()=>{this.drag=null}),this.svg.addEventListener("pointercancel",()=>{this.drag=null}),this.svg.addEventListener("wheel",n=>{n.preventDefault();const o=Math.exp(-n.deltaY*.0015);this.zoom=Math.max(.2,Math.min(20,this.zoom*o)),this.draw()},{passive:!1}),this.observer=new ResizeObserver(()=>this.draw()),this.observer.observe(t),this.draw()}fit(){this.zoom=1,this.pan={x:0,y:0},this.draw()}draw(){const t=Math.max(100,this.host.clientWidth),i=Math.max(100,this.host.clientHeight);this.svg.setAttribute("viewBox",`0 0 ${t} ${i}`);const n=this.bounds,o=Math.min((t-60)/(n.maxX-n.minX),(i-45)/(n.maxY-n.minY))*this.zoom,r=(n.minX+n.maxX)/2,l=(n.minY+n.maxY)/2;this.xy=d=>[t/2+(d.x-r)*o+this.pan.x,i/2-(d.y-l)*o+this.pan.y],this.svg.replaceChildren();const c=b("g",{class:"plot-grid"}),f=60/o,y=10**Math.floor(Math.log10(f)),p=[1,2,5,10].find(d=>d*y>=f)*y,g=r-(t/2+this.pan.x)/o,L=g+t/o,U=l+(i/2+this.pan.y)/o,$=U-i/o;for(let d=Math.ceil(g/p)*p;d<L;d+=p){const[m]=this.xy({x:d,y:0});c.append(b("line",{x1:m,x2:m,y1:0,y2:i})),c.append(b("text",{x:m+5,y:i-12},E(Math.abs(d)<p*1e-9?0:d)))}for(let d=Math.ceil($/p)*p;d<U;d+=p){const[,m]=this.xy({x:0,y:d});c.append(b("line",{x1:0,x2:t,y1:m,y2:m})),m<i-28&&c.append(b("text",{x:12,y:m-5},E(Math.abs(d)<p*1e-9?0:d)))}this.svg.append(c),this.robots=[];for(const[d,m]of this.recordings){const A=Re[d],de=Se(m.samples).map(({position:C})=>this.xy(C).join(",")).join(" ");if(this.svg.append(b("polyline",{points:de,fill:"none",stroke:A,"stroke-width":d==="candidate"?3:2.5,"stroke-dasharray":d==="baseline"?"7 5":"none","stroke-linecap":"round","stroke-linejoin":"round",opacity:.83})),d==="candidate"){const[C,Q]=this.xy(m.samples[0].position),[D,Y]=this.xy(m.world.goal);this.svg.append(b("circle",{cx:C,cy:Q,r:5,fill:"#fff",stroke:"#4c5554","stroke-width":2})),this.svg.append(b("text",{x:C-9,y:Q+24,class:"plot-label"},"Старт")),this.svg.append(b("circle",{cx:D,cy:Y,r:13,fill:"none",stroke:"#567a55","stroke-width":1.5,"stroke-dasharray":"3 3"})),this.svg.append(b("circle",{cx:D,cy:Y,r:5,fill:"#567a55"})),this.svg.append(b("text",{x:D+20,y:Y+4,class:"plot-label"},"Цель"));for(const H of m.events.filter(q=>!["START","GOAL"].includes(q.type))){const[q,pe]=this.xy(X(m.samples,H.t).position),ee=b("circle",{cx:q,cy:pe,r:5,fill:"#fff9ed",stroke:A,"stroke-width":2});ee.append(b("title",{},`${O(H.type)} · ${w(H.t)} с`)),this.svg.append(ee)}}const R=b("g");R.append(b("circle",{r:13,fill:A,opacity:.13})),R.append(b("path",{d:"M 10 0 L -6 -6 L -3 0 L -6 6 Z",fill:A,stroke:"white","stroke-width":1.5})),this.svg.append(R),this.robots.push({replay:m,marker:R})}this.setTime(this.time)}setTime(t){this.time=t;for(const{replay:i,marker:n}of this.robots??[]){const o=X(i.samples,t),[r,l]=this.xy(o.position);n.setAttribute("transform",`translate(${r} ${l}) rotate(${-o.orientation.yaw*180/Math.PI})`)}}dispose(){this.observer.disconnect(),this.svg.remove()}}document.querySelector("#root").innerHTML=ge;const a=e=>document.getElementById(e),h=e=>String(e??"").replace(/[&<>"']/g,t=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[t]),j=(e,t="")=>`<span class="badge ${h(t)}">${h(e)}</span>`,s={session:null,scenario:null,mode:location.hash==="#compare"?"compare":"replay",view:"top",time:0,duration:0,playing:!1,speed:1,loop:!1,events:[],renderer:null,renderVersion:0,frame:null,lastTick:null};function J(e,t=!1){a("app-alert").title="",a("app-alert").textContent=e||"",a("app-alert").hidden=!e,a("app-alert").classList.toggle("error",t)}function v(){s.playing=!1,cancelAnimationFrame(s.frame),s.frame=null,s.lastTick=null,a("play-button").textContent="▶",a("play-button").setAttribute("aria-label","Воспроизвести")}function G(){const e=s.scenario;return{candidate:e?.candidate.replay,baseline:s.mode==="compare"&&!e?.alignment_notice?e?.baseline?.replay:null}}function x(e){s.time=Math.max(0,Math.min(s.duration,e)),a("seek").value=s.time,a("seek").setAttribute("aria-valuetext",`${w(s.time)} из ${w(s.duration)} секунд`),a("time-display").textContent=`${w(s.time)} / ${w(s.duration)} с`,a("pose-time").textContent=`${w(s.time)} с`,s.renderer?.setTime(s.time);const t=s.scenario?.candidate.replay;if(t){const i=X(t.samples,s.time);a("live-pose").innerHTML=[["x",i.position.x,"м"],["y",i.position.y,"м"],["z",i.position.z,"м"],["Курс",i.orientation.yaw*180/Math.PI,"°"]].map(([n,o,r])=>`<div class="pose-cell">${n}<strong>${h(E(o,3))} ${r}</strong></div>`).join(""),a("sample-note").textContent=`Отсчётов: ${E(t.samples.length,0)} · ${s.time>t.samples.at(-1).t?"последнее записанное положение":"интерполяция положения"}`}else a("live-pose").textContent="Нет записи положения",a("sample-note").textContent="Метрики результата доступны ниже.";document.querySelectorAll(".track-cursor").forEach(i=>{i.style.left=`${s.duration?s.time/s.duration*100:0}%`}),a("previous-event").disabled=!s.events.some(i=>i.t<s.time-.001),a("next-event").disabled=!s.events.some(i=>i.t>s.time+.001)}function oe(e){if(s.playing){if(s.lastTick!==null){const t=s.time+Math.min((e-s.lastTick)/1e3,.25)*s.speed;if(t>=s.duration&&!s.loop){x(s.duration),v();return}x(s.loop?t%s.duration:t)}s.lastTick=e,s.frame=requestAnimationFrame(oe)}}function re(){if(s.duration){if(s.playing){v();return}s.time>=s.duration&&x(0),s.playing=!0,s.lastTick=null,a("play-button").textContent="Ⅱ",a("play-button").setAttribute("aria-label","Пауза"),s.frame=requestAnimationFrame(oe)}}function P(e){const t=e>0?s.events.find(i=>i.t>s.time+.001):s.events.findLast(i=>i.t<s.time-.001);t&&(v(),x(t.t))}function le(e){s.mode=e,history.replaceState(null,"",`#${e}`),s.scenario&&W()}function Ce(){const e=s.session,t=s.scenario,i=e.source==="demo"||t.candidate.replay?.runtime==="deterministic_demo";a("source-summary").innerHTML=["baseline","candidate"].filter(n=>t[n]).map(n=>`<div class="source-item"><span class="source-dot ${n}"></span><span>${M(n)}</span><span class="source-name" title="${h(t[n].label)}">${h(fe(t[n].label))}</span>${j(N(t[n].status),t[n].status==="PASS"?"pass":"fail")}</div>`).join(""),a("scenario-title").textContent=i&&t.name==="deterministic_demo"?"Демонстрационный маршрут":t.name,document.title=`RobotCI · ${a("scenario-title").textContent}`,a("workspace-subtitle").textContent=s.mode==="compare"?"Эталон и новый прогон на общей временной шкале.":"Изучайте траекторию, события и поведение робота.",a("source-badge").textContent=i?"Демонстрационные данные":e.gate?"Проверенные результаты":e.source==="suite"?"Результаты сценариев":"Replay v1",a("source-badge").className=`badge${i?" demo":""}`,a("scenario-count").textContent=e.scenarios.length,a("scenario-list").innerHTML=e.scenarios.map((n,o)=>`<button class="scenario-button" data-scenario="${o}" aria-current="${n.name===t.name}"><span class="scenario-dot ${n.comparison?.status==="REGRESSION"?"regression":""}"></span><span class="scenario-name">${h(e.source==="demo"&&n.name==="deterministic_demo"?"Демонстрационный маршрут":n.name)}</span></button>`).join(""),document.querySelectorAll("[data-mode]").forEach(n=>n.setAttribute("aria-current",n.dataset.mode===s.mode?"page":"false")),je(),a("export-button").textContent=e.gate?"↓ Скачать отчёт JSON":"↓ Скачать запись",a("session-footnote").textContent=i?"Демонстрационные данные · без проверки регрессий":e.gate?"Результат рассчитан модулем проверки регрессий RobotCI":"Просмотр без изменений · без проверки регрессий"}function Te(){const e=s.scenario;a("run-status").textContent=N(e.candidate.status),a("run-status").title=e.candidate.status,a("run-status").className=`badge ${e.candidate.status==="PASS"?"pass":"fail"}`,a("recorded-metrics").innerHTML=`<dl class="metric-list">${I.map(i=>`<div><dt>${h(i.label)}</dt><dd>${h(E(e.candidate.metrics[i.key]))}${Number.isFinite(e.candidate.metrics[i.key])&&i.unit?` ${i.unit}`:""}</dd></div>`).join("")}</dl>`;const t=s.session.gate;if(t){const i=e.comparison?.findings??[];a("gate-panel").innerHTML=`<div class="gate-title"><h3>Проверка регрессий</h3>${j(N(t.status),t.status.toLowerCase())}</div><p>Сравнены результаты с совместимыми задачами и параметрами среды.</p><div class="gate-summary ${t.status==="REGRESSION"?"regression":""}">${j(N(e.comparison?.status??"Недоступно"),e.comparison?.status?.toLowerCase())} <span>Превышений в сценарии: ${i.length}</span></div>${i.length?`<ul class="finding-list">${i.map(n=>`<li><span>${h(I.find(o=>o.key===n.metric)?.label??n.metric)}</span><strong>${h(V(n.increase_unbounded?1/0:n.increase,be(n.unit)))}</strong></li>`).join("")}</ul>`:""}<p>Допуски указаны ниже. Скачайте отчёт для значений с полной точностью.</p>`}else a("gate-panel").innerHTML=`<div class="gate-title"><h3>${e.baseline?"Сравнение записей":"Данные прогона"}</h3>${j("Без проверки")}</div><p title="${h(s.session.gate_notice)}">${h(S(s.session.gate_notice))}</p>${e.baseline?"":'<button id="add-baseline" class="button">Открыть записи для сравнения</button>'}`,a("add-baseline")?.addEventListener("click",Z)}function Ne(){const e=s.scenario,t=!!e.baseline,i=s.session.gate&&e.comparison;a("evidence-title").textContent=t?"Сравнение метрик":"Записанные метрики",a("evidence-badge").textContent=i?"Допуски проверены":t?"Сравнение записей":"Итоговые значения",a("metrics-head").innerHTML=`<tr><th scope="col">Метрика</th>${t?'<th scope="col">Эталон</th>':""}<th scope="col">Новый прогон</th>${t?'<th scope="col">Изменение</th>':""}${i?'<th scope="col">Допуск</th><th scope="col">Проверка</th>':""}</tr>`,a("metrics-body").innerHTML=I.map(n=>{const o=e.baseline?.metrics[n.key],r=e.candidate.metrics[n.key],l=e.alignment_notice?null:Le(o,r,n.deltaUnit),c=e.comparison?.findings.find(y=>y.metric===n.key),f=y=>`${E(y,6)}${Number.isFinite(y)&&n.unit?` ${n.unit}`:""}`;return`<tr class="${c?"metric-finding":""}"><td>${n.label}</td>${t?`<td title="${h(o)}">${f(o)}</td>`:""}<td title="${h(r)}">${f(r)}</td>${t?`<td class="${l>0?"increase":l<0?"decrease":""}">${V(l,n.deltaUnit)}</td>`:""}${i?`<td>≤ ${V(s.session.gate.policy[n.policy],n.deltaUnit)}</td><td>${c?"Превышен":"В допуске"}</td>`:""}</tr>`}).join(""),a("metrics-note").textContent=e.alignment_notice?"Разница скрыта: записи несовместимы для сравнения траекторий.":t?`Изменение = новый прогон − эталон. Длительность и путь — в процентах, остальные метрики — в абсолютных единицах.${i?"":" Эта разница сама по себе не определяет регрессию."}`:"Итоговые значения из записи или результата сценария. Они не меняются при перемотке."}function Oe(){s.events=_e(s.scenario,s.mode==="compare"&&!s.scenario.alignment_notice);const e=s.events.slice(0,1e3);a("event-count").textContent=`Всего: ${E(s.events.length,0)}${s.events.length>1e3?" · показаны первые 1 000":""}`,a("event-list").innerHTML=e.length?e.map((i,n)=>`<button class="event-row" data-event="${n}" title="Перейти к ${w(i.t)} с"><time>${w(i.t)} с</time><span><span class="event-description"><span class="source-dot ${i.source}"></span>${h(O(i.type))} <span class="microcopy">${M(i.source)}</span></span><small>${h(ve(i.message))}</small></span></button>`).join(""):'<p class="microcopy">События с временными метками не записаны. Их количество может быть указано в метриках результата.</p>';const t=Object.entries(G()).filter(([,i])=>i);a("event-tracks").innerHTML=t.map(([i])=>`<div class="event-track"><span>${M(i)}</span><div class="track-rail">${e.map((n,o)=>n.source===i?`<button class="track-event ${i}" data-event="${o}" style="left:${s.duration?n.t/s.duration*100:0}%" aria-label="${h(`${M(i)}: ${O(n.type)}, ${w(n.t)} с`)}" title="${h(`${O(n.type)} · ${w(n.t)} с`)}">◆</button>`:"").join("")}<span class="track-cursor"></span></div></div>`).join("")||'<span class="microcopy">Для воспроизведения нужна запись траектории.</span>',a("sync-note").textContent=t.length>1?"Общее время · в конце — последнее положение":"Время от начала · секунды"}async function K(){const e=++s.renderVersion;s.renderer?.dispose(),s.renderer=null,a("viewport").replaceChildren();const t=G(),i=Object.values(t).some(Boolean);if(a("plot-empty").hidden=i,a("fit-button").disabled=!i,a("scene-button").disabled=!i,a("top-button").setAttribute("aria-pressed",s.view==="top"),a("scene-button").setAttribute("aria-pressed",s.view==="3d"),a("frame-label").textContent=(t.candidate??t.baseline)?.world.frame?`Система координат: ${(t.candidate??t.baseline).world.frame}`:"",a("legend").innerHTML=Object.keys(t).filter(n=>t[n]).map(n=>`<span class="legend-item"><span class="legend-line ${n}"></span>${M(n)}</span>`).join(""),a("legend").hidden=!i,!i){a("plot-empty").innerHTML=`<strong>Траектория недоступна</strong><p title="${h(s.scenario.candidate.replay_notice)}">${h(S(s.scenario.candidate.replay_notice)||"Откройте запись Replay v1 для просмотра траектории.")}</p>`;return}try{if(s.view==="3d"){const{SceneView:n}=await he(async()=>{const{SceneView:o}=await import("./scene-view-IEu08m3D.js");return{SceneView:o}},[],import.meta.url);if(e!==s.renderVersion)return;s.renderer=new n(a("viewport"),t)}else s.renderer=new ie(a("viewport"),t)}catch{if(e!==s.renderVersion)return;s.view="top",a("viewport").replaceChildren(),s.renderer=new ie(a("viewport"),t),a("top-button").setAttribute("aria-pressed","true"),a("scene-button").setAttribute("aria-pressed","false"),J("3D недоступен в этом браузере. Полная записанная траектория доступна в виде сверху.",!0)}a("view-hint").textContent=s.view==="3d"?"Перетаскивание — поворот · колесо — масштаб":"Перетаскивание — сдвиг · колесо — масштаб",s.renderer?.setTime(s.time)}function W(){v();const e=G();s.duration=Math.max(0,...Object.values(e).filter(Boolean).map(i=>i.duration_sec)),s.time=0,a("seek").max=s.duration||1,a("seek").disabled=!s.duration,a("play-button").disabled=!s.duration;const t=[];s.mode==="compare"&&(s.scenario.baseline||t.push("Откройте эталонную запись для сравнения прогонов."),s.scenario.alignment_notice&&t.push(`${S(s.scenario.alignment_notice)} Показана только траектория нового прогона.`),s.scenario.baseline?.replay_notice&&t.push(`Эталон: ${S(s.scenario.baseline.replay_notice)}`)),s.scenario.candidate.replay_notice&&e.baseline&&t.push(`Новый прогон: ${S(s.scenario.candidate.replay_notice)}`),J(t.join(" ")),a("app-alert").title=[s.scenario.alignment_notice,s.scenario.baseline?.replay_notice,s.scenario.candidate.replay_notice].filter(Boolean).join(" "),Ce(),Te(),Ne(),Oe(),x(0),K()}function ce(e){if(e.schema_version!==1||!Array.isArray(e.scenarios)||!e.scenarios.length)throw new Error("Неподдерживаемый формат данных просмотра.");for(const t of e.scenarios)for(const i of["candidate","baseline"])t[i]?.replay&&F(t[i].replay);s.session=e,s.scenario=e.scenarios.find(t=>t.name===e.selected_scenario)??e.scenarios[0],W()}function Z(){v(),a("import-error").hidden=!0,a("open-dialog").showModal()}function je(){const e=a("export-button");s.exportURL&&URL.revokeObjectURL(s.exportURL),s.exportURL=null;const t=s.session.gate??s.scenario.candidate.replay;if(e.setAttribute("aria-disabled",String(!t)),!t){e.removeAttribute("href"),e.tabIndex=-1;return}e.tabIndex=0,e.download=s.session.gate?"robotci-suite-gate.json":`${s.scenario.name.replace(/[^a-zA-Z0-9_-]/g,"_")}.replay.json`,s.exportURL=URL.createObjectURL(new Blob([JSON.stringify(t,null,2)+`
`],{type:"application/json"})),e.href=s.exportURL}a("play-button").addEventListener("click",re);a("previous-event").addEventListener("click",()=>P(-1));a("next-event").addEventListener("click",()=>P(1));a("seek").addEventListener("input",e=>{v(),x(Number(e.target.value))});a("speed").addEventListener("change",e=>{s.speed=Number(e.target.value)});a("loop").addEventListener("change",e=>{s.loop=e.target.checked});a("fit-button").addEventListener("click",()=>s.renderer?.fit());a("top-button").addEventListener("click",()=>{s.view="top",K()});a("scene-button").addEventListener("click",()=>{s.view="3d",K()});a("open-button").addEventListener("click",Z);a("help-button").addEventListener("click",()=>{v(),a("help-dialog").showModal()});document.querySelector(".brand").addEventListener("click",e=>{e.preventDefault(),le("replay")});document.querySelectorAll("[data-mode]").forEach(e=>e.addEventListener("click",()=>le(e.dataset.mode)));document.querySelectorAll("[data-close]").forEach(e=>e.addEventListener("click",()=>a(e.dataset.close).close()));a("scenario-list").addEventListener("click",e=>{const t=e.target.closest("[data-scenario]");t&&(s.scenario=s.session.scenarios[Number(t.dataset.scenario)],W())});for(const e of["event-list","event-tracks"])a(e).addEventListener("click",t=>{const i=t.target.closest("[data-event]");i&&(v(),x(s.events[Number(i.dataset.event)].t))});a("open-form").addEventListener("submit",async e=>{e.preventDefault(),a("import-error").hidden=!0,a("import-button").disabled=!0,a("import-button").textContent="Чтение записей…";try{const t=a("candidate-file").files[0],i=a("baseline-file").files[0];if(!t)throw new Error("Сначала выберите запись нового прогона.");const n=async l=>{if(l.size>se)throw new Error(`${l.name}: размер превышает 32 МиБ.`);try{return we(await l.text())}catch(c){throw new Error(`${l.name}: ${c instanceof DOMException?"не удалось прочитать файл. Выберите его ещё раз.":c.message}`)}},[o,r]=await Promise.all([n(t),i?n(i):null]);s.mode=r?"compare":"replay",history.replaceState(null,"",`#${s.mode}`),ce(Ee(o,r,t.name,i?.name)),a("open-dialog").close(),a("open-form").reset()}catch(t){a("import-error").textContent=t.message,a("import-error").hidden=!1}finally{a("import-button").disabled=!1,a("import-button").textContent="Открыть"}});document.addEventListener("keydown",e=>{if(e.ctrlKey||e.metaKey||e.altKey||document.querySelector("dialog[open]")||e.target.closest("input,select,textarea,button,a,[contenteditable]"))return;const t={" ":re,ArrowLeft:()=>{v(),x(s.time-1)},ArrowRight:()=>{v(),x(s.time+1)},Home:()=>{v(),x(0)},End:()=>{v(),x(s.duration)},"[":()=>P(-1),"]":()=>P(1),f:()=>s.renderer?.fit(),o:Z,"?":()=>{v(),a("help-dialog").showModal()}},i={а:"f",щ:"o",х:"[",ъ:"]"},n=e.key.length===1?e.key.toLowerCase():e.key,o=t[i[n]??n];o&&(e.preventDefault(),o())});document.addEventListener("visibilitychange",()=>{document.hidden&&v()});window.addEventListener("pagehide",()=>{v(),s.renderVersion++,s.renderer?.dispose()});async function Ie(){try{const e=await fetch("/api/session",{cache:"no-store"});if(!e.ok)throw new Error(`Сервер вернул HTTP ${e.status}.`);ce(await e.json())}catch(e){const t=e instanceof TypeError?"Проверьте, запущен ли локальный сервер.":e instanceof SyntaxError?"Сервер вернул некорректный JSON.":e.message;a("source-badge").textContent="Нет соединения",J(`Не удалось загрузить данные. ${t} Вы можете открыть локальные записи.`,!0),a("plot-empty").hidden=!1,a("plot-empty").innerHTML="<strong>Откройте запись для начала</strong><p>Выберите запись нового прогона в формате Replay v1. При желании добавьте эталон.</p>"}}Ie();export{Re as C,Se as d,X as s,Me as t};
