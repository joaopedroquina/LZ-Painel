
/* LZ Widget desktop window — local time, hardware metrics and optional weather. */
(function(){
 'use strict';
 const $=s=>document.querySelector(s);
 const kind=decodeURIComponent((location.hash||'#pixel-clock').slice(1));
 const shades={blue:'#5a93ff',mint:'#38cda9',violet:'#a284fa',amber:'#f2bb5f',rose:'#f080ae'};
 let conf={accent:'blue',city:'',unit:'C',note:''},currentWeather=null;
 let weatherCity='',busy=false,live=true;
 function now(){
  const d=new Date();
  return {time:d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',hour12:false}),
   date:d.toLocaleDateString('pt-BR',{weekday:'short',day:'numeric',month:'short'}).replaceAll('.',''),
   weekday:d.toLocaleDateString('pt-BR',{weekday:'long'}),
   month:d.toLocaleDateString('pt-BR',{month:'long',year:'numeric'}),
   obj:d};
 }
 function days(){
  const d=new Date(),first=(new Date(d.getFullYear(),d.getMonth(),1).getDay()+6)%7;
  const n=new Date(d.getFullYear(),d.getMonth()+1,0).getDate();
  let markup=['S','T','Q','Q','S','S','D'].map(s=>'<span class="dayname">'+s+'</span>').join('');
  for(let i=0;i<first;i++)markup+='<span></span>';
  for(let i=1;i<=n;i++)markup+='<span class="'+(i===d.getDate()?'today':'')+'">'+i+'</span>';
  return markup;
 }
 function icon(code){
  if(code===0)return '☀';if(code<=3)return '☁';if(code<=48)return '≋';
  if(code<=67)return '☂';if(code<=77)return '❄';if(code<=82)return '☔';return '☁';
 }
 function view(type){
  if(type==='pixel-clock')return '<div class="wz-clock-pixel"><div class="wz-hr" data-hour>--</div><div class="wz-min" data-min>--</div><div class="wz-pixel-date" data-date>—</div></div>';
  if(type==='orbital-clock')return '<div class="wz-orbital"><div class="wz-orbit-dot" id="dwOrbitDot"></div><div><b id="dwNow">--:--</b><small id="dwWeekday">—</small></div></div>';
  if(type==='weather-dial')return '<div class="wz-dial"><i class="wz-arc"></i><span id="dwWeatherIcon">☁</span><strong id="dwTemp">--°</strong><small id="dwHumidity">Defina a cidade</small><footer id="dwCity"></footer></div>';
  if(type==='weather-glass')return '<div class="wz-glassweather"><header><small id="dwCity">Configure a cidade</small><span id="dwWeatherIcon">☀</span></header><strong id="dwTemp">--°</strong><small id="dwHumidity">Dados indisponíveis</small><small>Fonte: Open-Meteo</small></div>';
  if(type==='pc-pulse')return '<div class="wz-perfbox"><h4>PC · AO VIVO</h4><div class="wz-perfrow"><span>CPU</span><div class="wz-meter"><i id="dwCpuBar"></i></div><strong id="dwCpu">--%</strong></div><div class="wz-perfrow"><span>RAM</span><div class="wz-meter"><i id="dwRamBar"></i></div><strong id="dwRam">--%</strong></div><small style="font-size:10px;color:#94b1d3">Monitoramento do Windows</small></div>';
  if(type==='calendar')return '<div class="wz-calbox"><header class="wz-calhead"><strong id="dwMonth"></strong><span>✦</span></header><div class="wz-calendar" id="dwCalendar"></div></div>';
  if(type==='storage')return '<div class="wz-storagebox"><h4>ARMAZENAMENTO · WINDOWS</h4><div class="wz-storage-ring" id="dwDiskRing" data-value="--%"></div><small id="dwDiskFree">Espaço não disponível</small></div>';
  if(type==='network')return '<div class="wz-netbox"><h4>REDE · LATÊNCIA DE REFERÊNCIA</h4><div class="wz-ping" id="dwPing">-- ms</div><div class="wz-meter"><i id="dwPingBar"></i></div><small>Conexão com servidor externo, não é ping do jogo.</small></div>';
  if(type==='notes')return '<div class="wz-noteboard"><header>✧ MINHAS NOTAS</header><p id="dwNote"></p></div>';
  return '<div class="dw-empty">Modelo não encontrado.</div>';
 }
 function setText(selector,value){const el=$(selector);if(el)el.textContent=value}
 function setBar(selector,pct){const el=$(selector);if(el)el.style.width=Math.min(100,Math.max(0,Number(pct)||0))+'%'}
 function applyTheme(){
  document.documentElement.style.setProperty('--wz-accent',shades[conf.accent]||shades.blue);
  $('#dwShell').className='dw-shell '+
   (kind.includes('clock')?'clock-dark':kind.includes('weather')?'weather-dark':kind==='notes'?'note-dark':'');
 }
 function updateClock(){
  const n=now();
  const parts=n.time.split(':');
  setText('[data-hour]',parts[0]);setText('[data-min]',parts[1]);setText('[data-date]',n.date);
  setText('#dwNow',n.time);setText('#dwWeekday',n.weekday);
  if($('#dwOrbitDot')){
   const deg=(n.obj.getMinutes()+n.obj.getSeconds()/60)*6;
   $('#dwOrbitDot').style.transform='rotate('+deg+'deg) translateY(-84px)';
   $('#dwOrbitDot').style.transformOrigin='center 90px';
  }
  if($('#dwCalendar')){
   const key=n.obj.getFullYear()+'-'+n.obj.getMonth()+'-'+n.obj.getDate();
   if($('#dwCalendar').dataset.day!==key){$('#dwCalendar').dataset.day=key;$('#dwCalendar').innerHTML=days()}
   setText('#dwMonth',n.month);
  }
 }
 function showWeather(){
  const w=currentWeather,ok=!!w?.ok;
  setText('#dwCity',ok?w.city:(conf.city||'Digite sua cidade no painel'));
  setText('#dwWeatherIcon',ok?icon(w.weather_code):'☁');
  if(!ok){setText('#dwTemp','--°');setText('#dwHumidity',conf.city?'Clima indisponível':'Configure a cidade');return}
  const v=conf.unit==='F'?Number(w.temp_c)*9/5+32:Number(w.temp_c);
  setText('#dwTemp',Math.round(v)+'°');
  setText('#dwHumidity',w.humidity==null?'Umidade indisponível':'Umidade '+w.humidity+'%');
 }
 async function backend(method,...args){
  try{
   if(!window.pywebview?.api?.[method])return null;
   return await window.pywebview.api[method](...args);
  }catch(e){return null}
 }
 async function readWeather(){
  if(!kind.includes('weather'))return;
  const requested=String(conf.city||'').trim();
  weatherCity=requested;
  if(!requested){currentWeather=null;showWeather();return}
  const result=await backend('weather_for_city',requested);
  if(!live||weatherCity!==requested)return;
  currentWeather=result?.ok?result:null;
  showWeather();
 }
 async function readHardware(){
  if(!['pc-pulse','storage'].includes(kind))return;
  const s=await backend('stats');if(!s||!live)return;
  if(kind==='pc-pulse'){
   const cpu=Number.isFinite(s.cpu)?Math.round(s.cpu):null;
   const ram=Number.isFinite(s.ram_used)&&s.ram_total?Math.round(s.ram_used/s.ram_total*100):null;
   setText('#dwCpu',cpu===null?'N/D':cpu+'%');setText('#dwRam',ram===null?'N/D':ram+'%');
   setBar('#dwCpuBar',cpu);setBar('#dwRamBar',ram);
  }else{
   const pct=Number.isFinite(s.disk)?Math.round(s.disk):null;
   const ring=$('#dwDiskRing');
   if(ring){ring.style.background='conic-gradient(var(--wz-accent) '+(pct||0)+'%,#344157 0%)';ring.dataset.value=pct===null?'--%':pct+'%'}
   const available=Number.isFinite(s.disk_free)?(s.disk_free/2**30).toFixed(1).replace('.',',')+' GB livres':'Espaço indisponível';
   setText('#dwDiskFree',available);
  }
 }
 async function readNetwork(){
  if(kind!=='network'||busy)return;
  busy=true;
  const rows=await backend('ping');
  busy=false;
  if(!live)return;
  const vals=Array.isArray(rows)?rows.map(r=>r?.[1]).filter(n=>Number.isFinite(n)):[];
  if(!vals.length){setText('#dwPing','Sem sinal');setBar('#dwPingBar',0);return}
  const ms=Math.min(...vals);
  setText('#dwPing',ms+' ms');setBar('#dwPingBar',Math.max(8,100-ms/2));
 }
 function render(){
  $('#dwMain').innerHTML=view(kind);
  $('#dwSource').textContent=kind.includes('weather')?'Clima: Open-Meteo · conectado à internet':
    kind==='network'?'A latência pode variar por rede e servidor':'';
  applyTheme();updateClock();setText('#dwNote',conf.note||'Escreva sua anotação no LZ Painel…');
  showWeather();readHardware();readNetwork();
 }
 window.widgetConfigure=function(newConf){
  const oldCity=conf.city;
  conf=Object.assign({},conf,newConf&&typeof newConf==='object'?newConf:{});
  applyTheme();
  setText('#dwNote',conf.note||'Escreva sua anotação no LZ Painel…');
  showWeather();
  if(oldCity!==conf.city)readWeather();
 };
 let initialized=false;
 async function initialize(){
  if(initialized)return;
  if(!window.pywebview?.api?.widget_get_config)return;
  initialized=true;
  const config=await backend('widget_get_config',kind);
  if(config)window.widgetConfigure(config);
  render();readWeather();
 }
 $('#dwMain').innerHTML=view(kind);render();
 $('#dwClose').addEventListener('click',async()=>{
  live=false;
  const done=await backend('widget_close',kind);
  if(!done)window.close();
 });
 window.addEventListener('pywebviewready',initialize);
 let tries=0;
 const bridgePoll=setInterval(()=>{
  if(initialized||tries++>30){clearInterval(bridgePoll);return}
  initialize();
 },200);
 setInterval(updateClock,1000);
 setInterval(readHardware,5000);
 setInterval(readNetwork,45000);
 setInterval(readWeather,900000);
})();
