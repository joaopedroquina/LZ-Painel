
/* LZ Widget Studio: prévias verificáveis e janelas independentes no Windows. */
(function(){
 const palette={
  blue:'#5a93ff',mint:'#38cda9',violet:'#a284fa',amber:'#f2bb5f',rose:'#f080ae'
 };
 const types=[
  {id:'pixel-clock',name:'Pixel Clock',category:'clock',tag:'MINIMAL',desc:'Relógio digital pixelado e data, inspirado na referência.'},
  {id:'orbital-clock',name:'Orbit Clock',category:'clock',tag:'ANIMADO',desc:'Mostrador redondo com ponteiro de minutos e brilho suave.'},
  {id:'weather-dial',name:'Weather Arc',category:'weather',tag:'CLIMA',desc:'Arco minimalista com temperatura e umidade da cidade escolhida.'},
  {id:'weather-glass',name:'Weather Glass',category:'weather',tag:'GLASS',desc:'Cartão translúcido com condição e temperatura atual.'},
  {id:'pc-pulse',name:'PC Pulse',category:'system',tag:'AO VIVO',desc:'Uso real de CPU e memória RAM em barras animadas.'},
  {id:'calendar',name:'Mini Calendar',category:'utility',tag:'CALENDÁRIO',desc:'Calendário compacto com destaque para o dia de hoje.'},
  {id:'storage',name:'Storage Ring',category:'system',tag:'DISCO',desc:'Ocupação da unidade do Windows em um indicador circular.'},
  {id:'network',name:'Network Meter',category:'system',tag:'REDE',desc:'Latência de conexão medida pelo monitor de rede.'},
  {id:'notes',name:'Sticky Notes',category:'utility',tag:'NOTAS',desc:'Anotações personalizadas em estilo papel de vidro.'}
 ];
 const defaultPrefs={accent:'blue',city:'',unit:'C',on_top:false,note:''};
 const getPrefs=()=>Object.assign({},defaultPrefs,S.widgetPrefs||{});
 function weatherIcon(code){
  if(code===0)return '☀';if(code<=3)return '☁';if(code<=48)return '≋';
  if(code<=67)return '☂';if(code<=77)return '❄';if(code<=82)return '☔';return '☁';
 }
 function dates(){
  const date=new Date(),hours=String(date.getHours()).padStart(2,'0'),minutes=String(date.getMinutes()).padStart(2,'0');
  return {date,hours,minutes,hhmm:hours+':'+minutes,
   caption:date.toLocaleDateString('pt-BR',{weekday:'short',day:'numeric',month:'short'}).replaceAll('.',''),
   weekday:date.toLocaleDateString('pt-BR',{weekday:'long'}),
   month:date.toLocaleDateString('pt-BR',{month:'long',year:'numeric'})};
 }
 function calendarMarkup(){
  const d=new Date(),month=d.getMonth(),year=d.getFullYear();
  const monday=(new Date(year,month,1).getDay()+6)%7;
  const days=new Date(year,month+1,0).getDate();
  let text=['S','T','Q','Q','S','S','D'].map(t=>'<span class="dayname">'+t+'</span>').join('');
  for(let n=0;n<monday;n++)text+='<span></span>';
  for(let day=1;day<=days;day++)text+='<span class="'+(day===d.getDate()?'today':'')+'">'+day+'</span>';
  return text;
 }
 function preview(kind){
  if(kind==='pixel-clock')return '<div class="wz-clock-pixel"><span class="wz-hr" data-wz-hour>--</span><span class="wz-min" data-wz-minute>--</span><span class="wz-pixel-date" data-wz-date>...</span></div>';
  if(kind==='orbital-clock')return '<div class="wz-orbital"><div class="wz-orbit-dot" data-wz-orbit></div><div><b data-wz-hhmm>--:--</b><small data-wz-weekday>...</small></div></div>';
  if(kind==='weather-dial')return '<div class="wz-dial"><i class="wz-arc"></i><span data-wz-weather-icon>☁</span><strong data-wz-weather-temp>--°</strong><small data-wz-weather-hum>Defina a cidade</small><footer data-wz-weather-city>Widget de clima</footer></div>';
  if(kind==='weather-glass')return '<div class="wz-glassweather"><header><small data-wz-weather-city>Sua cidade</small><span data-wz-weather-icon>☀</span></header><strong data-wz-weather-temp>--°</strong><small data-wz-weather-hum>Configure a previsão do tempo</small><small>Fonte: Open-Meteo</small></div>';
  if(kind==='pc-pulse')return '<div class="wz-perfbox"><h4>DESEMPENHO DO PC</h4><div class="wz-perfrow"><span>CPU</span><div class="wz-meter"><i data-wz-cpu-bar></i></div><strong data-wz-cpu>--%</strong></div><div class="wz-perfrow"><span>RAM</span><div class="wz-meter"><i data-wz-ram-bar></i></div><strong data-wz-ram>--%</strong></div><small style="color:#9baccc">Métricas do Windows · atualizado em tempo real</small></div>';
  if(kind==='calendar')return '<div class="wz-calbox"><header class="wz-calhead"><strong data-wz-month>Mês atual</strong><span>✦</span></header><div class="wz-calendar" data-wz-calendar>'+calendarMarkup()+'</div></div>';
  if(kind==='storage')return '<div class="wz-storagebox"><h4>ARMAZENAMENTO</h4><div class="wz-storage-ring" data-wz-storage-ring data-value="--%"></div><small data-wz-storage>Espaço livre indisponível</small></div>';
  if(kind==='network')return '<div class="wz-netbox"><h4>CONEXÃO / PING</h4><div class="wz-ping" data-wz-network>-- ms</div><div class="wz-meter"><i data-wz-network-bar></i></div><small>Latência medida a um servidor externo</small></div>';
  return '<div class="wz-noteboard"><header>✧ MINHAS NOTAS</header><p data-wz-note>Escreva algo nas opções...</p></div>';
 }
 function card(def,open){
  const flag=open?' <span class="wz-live">Aberto</span>':' <span class="wz-tag">'+def.tag+'</span>';
  const cls=def.category==='weather'?(def.id==='weather-glass'?'wz-glass':'wz-weather'):
    def.category==='system'?'wz-metrics':def.category==='utility'?'wz-note-bg':'';
  return '<article class="wz-card" data-wz-card="'+def.id+'" data-wz-category="'+def.category+'">'+
   '<div class="wz-preview '+cls+'">'+preview(def.id)+'</div>'+
   '<div class="wz-body"><div class="wz-name"><b>'+def.name+'</b>'+flag+'</div><p>'+def.desc+'</p>'+
   '<div class="wz-actions"><button type="button" data-wz-open="'+def.id+'">'+(open?'◉ Mostrar':'▣ Abrir no desktop')+'</button>'+
   (open?'<button type="button" class="wz-remove" data-wz-close="'+def.id+'">Fechar</button>':'')+'</div></div></article>';
 }
 const setText=(selector,text,context=document)=>{
  context.querySelectorAll(selector).forEach(el=>el.textContent=text);
 };
 function setBar(selector,value,context=document){
  const percent=Math.max(0,Math.min(100,Number(value)||0));
  context.querySelectorAll(selector).forEach(el=>el.style.width=percent+'%');
 }
 function refreshClock(root){
  if(!root||!root.isConnected)return;
  const d=dates();
  setText('[data-wz-hour]',d.hours,root);setText('[data-wz-minute]',d.minutes,root);
  setText('[data-wz-date]',d.caption,root);setText('[data-wz-hhmm]',d.hhmm,root);
  setText('[data-wz-weekday]',d.weekday,root);setText('[data-wz-month]',d.month,root);
  root.querySelectorAll('[data-wz-orbit]').forEach(e=>{
   const deg=(d.date.getMinutes()+d.date.getSeconds()/60)*6;
   e.style.transform='rotate('+deg+'deg) translateY(-77px)';
   e.style.transformOrigin='center 83px';
  });
 }
 function updateWeather(root,data,prefs){
  const valid=data&&data.ok===true,city=valid?data.city:(prefs.city||'Sua cidade');
  const temp=valid?Number(data.temp_c):null;
  const converted=valid?(prefs.unit==='F'?Math.round(temp*9/5+32):Math.round(temp)):null;
  setText('[data-wz-weather-temp]',valid?converted+'°':'--°',root);
  setText('[data-wz-weather-city]',city,root);
  setText('[data-wz-weather-icon]',valid?weatherIcon(data.weather_code):'☁',root);
  setText('[data-wz-weather-hum]',valid?(data.humidity===null?'Umidade indisponível':'Umidade '+data.humidity+'%'):
    (prefs.city?'Sem dados disponíveis':'Defina a cidade'),root);
 }
 V.pers=async()=>{
  const original=getPrefs();
  S.widgetPrefs=original;save();
  const current=await A('widget_list'),active=new Set(Array.isArray(current)?current:[]);
  const heading='<div class="wz-hero"><div><span class="wz-eyebrow">LZ STUDIO · PERSONALIZAÇÃO</span><h2>Seu desktop, do seu jeito.</h2>'+
   '<p>Escolha widgets com aparência minimalista, ajuste as cores e coloque-os diretamente na área de trabalho do Windows.</p>'+
   '<div class="wz-hero-stats"><span>✧ <strong>9</strong> modelos</span><span>◉ <strong id="wzActiveCount">'+active.size+'</strong> ativos</span><span>◷ Atualização automática</span></div></div><div class="wz-hero-icon">◷</div></div>';
  const colors=Object.keys(palette).map(k=>'<button title="'+k+'" aria-label="Cor '+k+'" type="button" data-wz-accent="'+k+'" class="wz-swatch '+(original.accent===k?'on':'')+'" style="--tone:'+palette[k]+'"></button>').join('');
  const controls='<div class="wz-controls"><div class="wz-control"><div class="wz-control-label">01 / Sua paleta</div><div class="wz-swatches">'+colors+'</div><small>Altere o brilho de todos os widgets abertos.</small></div>'+
   '<div class="wz-control"><div class="wz-control-label">02 / Clima e unidades</div><div class="wz-fieldpair"><input id="wzCity" class="wz-field" maxlength="60" placeholder="Digite uma cidade" value="'+esc(original.city)+'"/><select id="wzUnit" class="wz-field"><option value="C" '+(original.unit==='C'?'selected':'')+'>°C</option><option value="F" '+(original.unit==='F'?'selected':'')+'>°F</option></select></div><small>Clima somente da cidade escolhida por você.</small></div>'+
   '<div class="wz-control"><div class="wz-control-label">03 / Posição e notas</div><label class="wz-on-top"><input type="checkbox" id="wzTop" '+(original.on_top?'checked':'')+'> Manter novos widgets sobre as janelas</label><input type="text" class="wz-field" id="wzNote" maxlength="400" placeholder="Sua anotação..." value="'+esc(original.note)+'"/><small>Arraste os widgets pela faixa superior.</small></div></div>';
  const filters=[['all','Todos'],['clock','Relógios'],['weather','Clima'],['system','Sistema'],['utility','Utilidade']];
  const nav='<div class="wz-filterbar">'+filters.map(([id,text])=>'<button type="button" class="wz-filter '+(id==='all'?'on':'')+'" data-wz-filter="'+id+'">'+text+'</button>').join('')+'</div>';
  const gallery='<div class="wz-grid" id="wzGallery">'+types.map(t=>card(t,active.has(t.id))).join('')+'</div>';
  const footer='<p class="wz-footer">Relógios usam a hora do Windows; CPU, RAM, disco e ping são obtidos do PC. Clima: Open-Meteo, requer internet e cidade configurada. Para distribuir comercialmente, confirme as condições de licença do provedor.</p>';
  const body='<section class="wz-page" id="wzPage">'+heading+controls+'<div class="wz-section-head"><h3>Biblioteca de widgets</h3><p>Prévia ao vivo · clique para adicionar ao desktop</p></div>'+nav+gallery+footer+'</section>';
  return [body,()=>{
   const root=$('#wzPage');if(!root)return;
   let activeFilter='all',ticker,hardwareTimer,weatherTimer,networkTimer;
   let latestWeather=null,alive=true;
   const prefs=()=>getPrefs();
   const applyPalette=()=>root.style.setProperty('--wz-accent',palette[prefs().accent]||palette.blue);
   const listCards=()=>{
    const target=$('#wzGallery');if(!target)return;
    target.innerHTML=types.filter(t=>activeFilter==='all'||t.category===activeFilter)
      .map(t=>card(t,active.has(t.id))).join('');
    bindCards();applyPalette();refreshClock(root);
    setText('[data-wz-note]',prefs().note||'Escreva algo nas opções...',root);
    updateWeather(root,latestWeather,prefs());
   };
   const store=()=>{
    S.widgetPrefs=Object.assign({},prefs(),{
     city:$('#wzCity')?.value.trim()||'',unit:$('#wzUnit')?.value||'C',
     note:$('#wzNote')?.value||'',on_top:!!$('#wzTop')?.checked
    });save();applyPalette();
    for(const kind of active)A('widget_update',kind,S.widgetPrefs);
    setText('[data-wz-note]',S.widgetPrefs.note||'Escreva algo nas opções...',root);
   };
   const loadWeather=async()=>{
    const config=prefs(),city=config.city;
    if(!city){latestWeather=null;updateWeather(root,null,config);return}
    const result=await A('weather_for_city',city);
    if(!alive||!root.isConnected||city!==prefs().city)return;
    latestWeather=result?.ok?result:null;
    updateWeather(root,latestWeather,prefs());
   };
   const loadHardware=async()=>{
    const s=await A('stats');
    if(!alive||!root.isConnected||!s)return;
    const cpu=Number.isFinite(s.cpu)?Math.round(s.cpu):null;
    const ram=Number.isFinite(s.ram_used)&&s.ram_total?Math.round(s.ram_used/s.ram_total*100):null;
    setText('[data-wz-cpu]',cpu===null?'N/D':cpu+'%',root);
    setText('[data-wz-ram]',ram===null?'N/D':ram+'%',root);
    setBar('[data-wz-cpu-bar]',cpu,root);setBar('[data-wz-ram-bar]',ram,root);
    const usage=Number.isFinite(s.disk)?Math.round(s.disk):null;
    root.querySelectorAll('[data-wz-storage-ring]').forEach(e=>{
      e.style.background='conic-gradient(var(--wz-accent) '+(usage||0)+'%,#344157 0%)';
      e.dataset.value=usage===null?'--%':usage+'%';
    });
    setText('[data-wz-storage]',Number.isFinite(s.disk_free)?'Livre: '+fmt(s.disk_free):'Espaço não disponível',root);
   };
   const loadNetwork=async()=>{
    const res=await A('ping');if(!alive||!root.isConnected)return;
    const ms=Array.isArray(res)?res.map(x=>x?.[1]).filter(n=>Number.isFinite(n)):[],min=ms.length?Math.min(...ms):null;
    setText('[data-wz-network]',min===null?'Sem sinal':min+' ms',root);
    setBar('[data-wz-network-bar]',min===null?0:Math.max(8,100-Math.min(min,200)/2),root);
   };
   const bindCards=()=>{
    root.querySelectorAll('[data-wz-open]').forEach(b=>b.onclick=async()=>{
      const id=b.dataset.wzOpen;
      if(typeof window.pywebview?.api?.widget_open!=='function'){
       toast('Prévia disponível. Abra o Painel.exe no Windows para mostrar widgets no desktop.');
       return;
      }
      store();b.disabled=true;
      const result=await A('widget_open',id,prefs());
      if(result?.ok){active.add(id);$('#wzActiveCount').textContent=active.size;listCards();toast('Widget aberto! Arraste pela faixa superior para posicionar.')}
      else{b.disabled=false;toast(result?.error||'Não foi possível abrir o widget.')}
    });
    root.querySelectorAll('[data-wz-close]').forEach(b=>b.onclick=async()=>{
      const id=b.dataset.wzClose;
      if(await A('widget_close',id)){active.delete(id);$('#wzActiveCount').textContent=active.size;listCards();toast('Widget fechado.')}
      else toast('Não foi possível fechar a janela.');
    });
   };
   root.querySelectorAll('[data-wz-filter]').forEach(b=>b.onclick=()=>{
      activeFilter=b.dataset.wzFilter;
      root.querySelectorAll('[data-wz-filter]').forEach(x=>x.classList.toggle('on',x===b));
      listCards();
   });
   root.querySelectorAll('[data-wz-accent]').forEach(b=>b.onclick=()=>{
     S.widgetPrefs=Object.assign({},prefs(),{accent:b.dataset.wzAccent});save();store();
     root.querySelectorAll('[data-wz-accent]').forEach(x=>x.classList.toggle('on',x===b));
   });
   $('#wzCity').addEventListener('change',()=>{store();loadWeather()});
   $('#wzCity').addEventListener('keydown',event=>{if(event.key==='Enter')event.target.blur()});
   $('#wzUnit').addEventListener('change',()=>{store();updateWeather(root,latestWeather,prefs())});
   $('#wzNote').addEventListener('change',store);
   $('#wzTop').addEventListener('change',store);
   applyPalette();listCards();refreshClock(root);
   ticker=setInterval(()=>refreshClock(root),1000);
   hardwareTimer=setInterval(loadHardware,5000);
   networkTimer=setInterval(loadNetwork,45000);
   weatherTimer=setInterval(loadWeather,900000);
   loadHardware();loadNetwork();loadWeather();
   window.__wzCleanup=()=>{
     alive=false;clearInterval(ticker);clearInterval(hardwareTimer);
     clearInterval(networkTimer);clearInterval(weatherTimer);
     if(window.__wzCleanup)window.__wzCleanup=null;
   };
  }];
 };
})();
