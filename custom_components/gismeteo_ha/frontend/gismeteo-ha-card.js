/* Gismeteo HA Weather Card 4.0.0 | CC BY-NC-SA 4.0 */
const CARD_TAG = 'gismeteo-ha-card';
const EDITOR_TAG = 'gismeteo-ha-card-editor';
const translations = {
  vi: { compact:'Thu gọn', detailed:'Chi tiết', humidity:'Độ ẩm', apparent:'Cảm nhận', pressure:'Áp suất', wind:'Gió', gust:'Gió giật', cloud:'Mây', vis:'Tầm nhìn', uv:'Chỉ số UV', dew:'Điểm sương', rain:'Lượng mưa', hourly:'Theo giờ', daily:'Theo ngày', now:'Hiện tại', no_data:'Đang chờ dữ liệu thời tiết…', unavailable:'Không có dữ liệu nguồn', updated:'Cập nhật', today:'Hôm nay', tomorrow:'Ngày mai', configure:'Chọn thực thể thời tiết', condition:{sunny:'Nắng', 'clear-night':'Trời quang', cloudy:'Nhiều mây', partlycloudy:'Có mây', rainy:'Mưa', pouring:'Mưa lớn', snowy:'Tuyết', 'snowy-rainy':'Mưa tuyết', lightning:'Dông', 'lightning-rainy':'Dông mưa', fog:'Sương mù', windy:'Nhiều gió', 'windy-variant':'Có gió', hail:'Mưa đá', exceptional:'Thời tiết cực đoan'} },
  en: { compact:'Compact', detailed:'Details', humidity:'Humidity', apparent:'Feels like', pressure:'Pressure', wind:'Wind', gust:'Gusts', cloud:'Clouds', vis:'Visibility', uv:'UV index', dew:'Dew point', rain:'Rain', hourly:'Hourly', daily:'Daily', now:'Now', no_data:'Waiting for weather data…', unavailable:'Source unavailable', updated:'Updated', today:'Today', tomorrow:'Tomorrow', configure:'Select a weather entity', condition:{} }
};
const glyph = {sunny:'☀️', 'clear-night':'🌙', cloudy:'☁️', partlycloudy:'🌤️', rainy:'🌧️', pouring:'🌧️', snowy:'❄️', 'snowy-rainy':'🌨️', lightning:'⛈️', 'lightning-rainy':'⛈️', fog:'🌫️', windy:'🌬️', 'windy-variant':'🌬️', hail:'🌨️', exceptional:'⚠️'};
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isNum = n => typeof n === 'number' && Number.isFinite(n);
const num = (n, digits=0) => isNum(n) ? n.toLocaleString(undefined,{maximumFractionDigits:digits}) : '—';
const readable = (value, unit='', digits=0) => isNum(value) ? `${num(value,digits)}${unit?' '+unit:''}` : '—';
const CSS = `
  :host{display:block;--gh-white:#f9fbff;--gh-sub:#c6d6f2}
  ha-card{position:relative;overflow:hidden;color:var(--gh-white);border:1px solid rgba(255,255,255,.18);border-radius:24px;background:linear-gradient(128deg,#12214c 0%,#153b75 54%,#1685ae 120%);box-shadow:0 16px 35px rgba(6,27,62,.24);font-family:var(--primary-font-family,Inter,system-ui,sans-serif);isolation:isolate}
  ha-card.rainy{background:linear-gradient(128deg,#101c36,#2d5074 62%,#437c9e)}
  ha-card.night{background:linear-gradient(128deg,#171e3d,#24366d 68%,#48518b)}
  ha-card.sunny{background:linear-gradient(118deg,#09558d,#0c88bc 59%,#e29d39)}
  .aura{position:absolute;z-index:-1;width:260px;height:260px;right:-75px;top:-110px;border-radius:50%;background:radial-gradient(circle,rgba(255,229,129,.25),transparent 68%);animation:breathe 9s ease-in-out infinite;pointer-events:none}
  .wrap{padding:22px 22px 20px}
  .top,.statusline,.actions,.forecast-header,.forecast-item{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .eyebrow{font-size:11px;font-weight:750;letter-spacing:.14em;color:#c5e6ff;text-transform:uppercase}
  .city{font-size:20px;font-weight:750;line-height:1.25;overflow-wrap:anywhere;margin-top:4px}
  .chip{appearance:none;border:1px solid rgba(255,255,255,.26);border-radius:30px;background:rgba(255,255,255,.12);color:#fff;cursor:pointer;padding:9px 13px;font:inherit;font-size:12px;font-weight:650;white-space:nowrap;transition:background .2s,transform .2s}
  .chip:hover,.chip:focus-visible{background:rgba(255,255,255,.24)} .chip:active{transform:scale(.96)} .chip[aria-pressed="true"]{background:rgba(255,255,255,.27)}
  .hero{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:20px 0 18px}
  .temp{font-size:clamp(54px,9vw,74px);font-weight:740;line-height:1;letter-spacing:-.06em;font-variant-numeric:tabular-nums}
  .condition{font-size:16px;font-weight:620;margin:9px 0 3px}
  .meta{color:var(--gh-sub);font-size:12px;line-height:1.45}
  .weather-symbol{font-size:clamp(70px,13vw,100px);line-height:1;filter:drop-shadow(0 14px 16px rgba(0,0,0,.2));animation:float 5.5s ease-in-out infinite;text-align:center}
  .stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
  .metric{min-width:0;padding:12px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.09);border-radius:15px}
  .metric .k{display:flex;align-items:center;gap:5px;color:#d3e7fc;font-size:11px;margin-bottom:9px;min-height:14px}.metric .v{font-size:16px;font-weight:700;word-break:break-word;font-variant-numeric:tabular-nums}
  .compact .wrap{padding:17px 19px}.compact .hero{padding:8px 0 16px}.compact .temp{font-size:55px}.compact .weather-symbol{font-size:66px}.compact .stats{grid-template-columns:repeat(3,minmax(0,1fr))}.compact .metric{padding:10px}.compact .metric .k{margin-bottom:5px}
  .divider{height:1px;background:rgba(255,255,255,.18);margin:18px 0 15px}
  .forecast-header{margin-bottom:13px}.section-title{font-size:14px;font-weight:750}.tabs{display:flex;gap:4px;padding:3px;border-radius:16px;background:rgba(0,0,0,.14)}.tabs .chip{border:0;padding:7px 12px}
  .forecast-list{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px}
  .forecast-item{min-width:0;flex-direction:column;gap:6px;padding:10px 3px;background:rgba(255,255,255,.08);border-radius:13px;font-size:12px;text-align:center}
  .forecast-item .time{color:#d7e9fc;font-size:11px;white-space:nowrap}.forecast-item .icon{font-size:24px}.forecast-item .f-temp{font-size:15px;font-weight:750}
  .statusline{margin-top:14px;font-size:11px;color:#c4ddf1}.statusline .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#71efbe;margin-right:5px}
  .empty{padding:24px 4px;color:#e2ecf5;font-size:13px}.sr{position:absolute;left:-10000px;width:1px;height:1px;overflow:hidden}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-7px)}}@keyframes breathe{0%,100%{opacity:.7;transform:scale(1)}50%{opacity:1;transform:scale(1.13)}}
  @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
  @media(max-width:360px){.wrap{padding:16px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.forecast-list{gap:4px}.forecast-item{font-size:11px}}
`;

class GismeteoHACard extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._config={};this._mode='detailed';this._tab='hourly';this._forecasts={hourly:[],daily:[]};this._unsubs=[];this._connected=false;}
  static getConfigElement(){return document.createElement(EDITOR_TAG);}
  static getStubConfig(hass){return {entity:Object.keys(hass?.states||{}).find(k=>k.startsWith('weather.'))||'',mode:'detailed',show_forecast:true};}
  setConfig(c){if(!c||typeof c!=='object')throw Error('Configuration required');const old=this._config.entity;this._config={mode:'detailed',show_forecast:true,...c};if(!['detailed','compact'].includes(this._config.mode))throw Error('mode must be detailed or compact');this._mode=this._config.mode;if(old!==this._config.entity)this._resubscribe();this._render();}
  set hass(h){this._hass=h;if(this.isConnected)this._resubscribe();this._render();}
  connectedCallback(){this._connected=true;this._resubscribe();this._render();}
  disconnectedCallback(){this._connected=false;this._unsubscribe();}
  getCardSize(){return this._mode==='compact'?3:6;}
  getGridOptions(){return {columns:12,rows:this._mode==='compact'?3:6,min_columns:4};}
  _unsubscribe(){for(const fn of this._unsubs){Promise.resolve(fn).then(u=>{if(typeof u==='function')u();}).catch(()=>{});}this._unsubs=[];this._subKey=null;}
  _resubscribe(){const h=this._hass,e=this._config.entity;if(!this._connected||!h?.connection?.subscribeMessage||!e)return;const key=e+'|'+String(h.connection);if(this._subKey===key)return;this._unsubscribe();this._subKey=key;this._forecasts={daily:[],hourly:[]};for(const type of ['daily','hourly']){let dead=false;const promise=h.connection.subscribeMessage(event=>{if(!dead&&this._config.entity===e){this._forecasts[type]=Array.isArray(event?.forecast)?event.forecast:[];this._render();}}, {type:'weather/subscribe_forecast',forecast_type:type,entity_id:e}).catch(err=>{this._forecasts[type]=[];this._render();return null});this._unsubs.push(promise.then(unsub=>()=>{dead=true;if(unsub)unsub();}));}}
  _t(){return translations[(this._hass?.language||'en').toLowerCase().startsWith('vi')?'vi':'en'];}
  _render(){if(!this._hass||!this.isConnected)return;const e=this._config.entity||Object.keys(this._hass.states).find(k=>k.startsWith('weather.'));const state=e?this._hass.states[e]:null;const a=state?.attributes||{};const t=this._t();const condition=state?.state||'unknown';const rain=['rainy','pouring','lightning-rainy','lightning','snowy-rainy'].includes(condition);const night=condition==='clear-night';const bright=condition==='sunny';const displayTitle=this._config.name||a.friendly_name||'Gismeteo HA';const feel=readable(a.apparent_temperature,'°',1);const metric=(label,value,icon)=>`<div class="metric"><div class="k"><span aria-hidden="true">${icon}</span>${esc(label)}</div><div class="v">${esc(value)}</div></div>`;const weatherSymbol=glyph[condition]||'🌤️';const cond=t.condition[condition]||condition.replaceAll('-',' ');const metrics=[
  metric(t.humidity,readable(a.humidity,'%'),'💧'),metric(t.wind,readable(a.wind_speed,a.wind_speed_unit||'km/h',1),'🌬️'),metric(t.pressure,readable(a.pressure,a.pressure_unit||'hPa',1),'📊'),
  metric(t.cloud,readable(a.cloud_coverage,'%'),'☁️'),metric(t.gust,readable(a.wind_gust_speed,a.wind_speed_unit||'km/h',1),'💨'),metric(t.vis,readable(a.visibility,a.visibility_unit||'km',1),'👁️'),
  metric(t.uv,readable(a.uv_index),'☀️'),metric(t.rain,readable(a.precipitation,a.precipitation_unit||'mm',1),'🌧️')
 ];const compact=this._mode==='compact';const forecast=this._forecasts[this._tab]||[];const tz=this._hass?.config?.time_zone;const dt=f=>{const x=new Date(f.datetime);if(!Number.isFinite(x.valueOf()))return '—';return this._tab==='hourly'?x.toLocaleTimeString(this._hass.language||'en',{hour:'2-digit',minute:'2-digit',...(tz?{timeZone:tz}:{})}):x.toLocaleDateString(this._hass.language||'en',{weekday:'short',...(tz?{timeZone:tz}:{})});};const items=forecast.slice(0,5).map(f=>`<div class="forecast-item"><span class="time">${esc(dt(f))}</span><span class="icon" aria-hidden="true">${glyph[f.condition]||'🌤️'}</span><span class="f-temp">${esc(readable(f.temperature,'°'))}</span>${isNum(f.precipitation_probability)?`<span class="time">💧 ${num(f.precipitation_probability)}%</span>`:''}</div>`).join('');const last=state?.last_updated?new Date(state.last_updated).toLocaleTimeString(this._hass.language||'en',{hour:'2-digit',minute:'2-digit',...(tz?{timeZone:tz}:{})}):'—';
    this.shadowRoot.innerHTML=`<style>${CSS}</style><ha-card class="${compact?'compact ':''}${rain?'rainy ':''}${night?'night ':''}${bright?'sunny':''}"><div class="aura"></div><div class="wrap"><div class="top"><div><div class="eyebrow">Gismeteo HA · ${esc(t.now)}</div><div class="city">${esc(displayTitle)}</div></div><button type="button" class="chip" data-action="mode" aria-label="${compact?esc(t.detailed):esc(t.compact)}">${compact?'⊞ '+esc(t.detailed):'▣ '+esc(t.compact)}</button></div>${state&&!['unknown','unavailable'].includes(condition)?`<div class="hero"><div><div class="temp">${esc(readable(a.temperature,'°',1))}</div><div class="condition">${esc(cond)}</div><div class="meta">${esc(t.apparent)} ${esc(feel)}</div></div><div class="weather-symbol" role="img" aria-label="${esc(cond)}">${weatherSymbol}</div></div><div class="stats">${(compact?metrics.slice(0,3):metrics).join('')}</div>${!compact&&this._config.show_forecast!==false?`<div class="divider"></div><div class="forecast-header"><span class="section-title">${this._tab==='hourly'?esc(t.hourly):esc(t.daily)}</span><div class="tabs"><button type="button" class="chip" data-action="tab" data-tab="hourly" aria-pressed="${this._tab==='hourly'}">${esc(t.hourly)}</button><button type="button" class="chip" data-action="tab" data-tab="daily" aria-pressed="${this._tab==='daily'}">${esc(t.daily)}</button></div></div>${items?`<div class="forecast-list">${items}</div>`:`<div class="meta">${esc(t.no_data)}</div>`}`:''}<div class="statusline"><span><span class="dot"></span>${esc(t.updated)} ${esc(last)}</span><span>Gismeteo</span></div>`:`<div class="empty">${esc(e?t.no_data:t.configure)}</div>`}</div></ha-card>`;
    this.shadowRoot.querySelectorAll('button[data-action]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.action==='mode')this._mode=this._mode==='compact'?'detailed':'compact';if(b.dataset.action==='tab')this._tab=b.dataset.tab;this._render();}));
  }
}
class GismeteoHAEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._config={};}
  setConfig(config){this._config={mode:'detailed',show_forecast:true,...config};this._render();}
  set hass(hass){this._hass=hass;this._render();}
  _update(patch){this._config={...this._config,...patch};this.dispatchEvent(new CustomEvent('config-changed',{bubbles:true,composed:true,detail:{config:this._config}}));}
  _render(){if(!this.shadowRoot)return;const entries=Object.entries(this._hass?.states||{}).filter(([key])=>key.startsWith('weather.'));this.shadowRoot.innerHTML=`<style>:host{display:block;font:inherit;color:var(--primary-text-color)}.row{margin:14px 0}label{display:block;font-size:13px;font-weight:600;margin-bottom:6px}select,input{box-sizing:border-box;display:block;width:100%;font:inherit;padding:11px;border:1px solid var(--divider-color,#888);border-radius:9px;color:var(--primary-text-color);background:var(--card-background-color,#fff)}.toggle{display:flex;align-items:center;gap:10px}</style><div class="row"><label for="entity">Weather entity</label><select id="entity"><option value="">Select entity</option>${entries.map(([key,st])=>`<option value="${esc(key)}" ${this._config.entity===key?'selected':''}>${esc(st.attributes.friendly_name||key)}</option>`).join('')}</select></div><div class="row"><label for="name">Card title (optional)</label><input id="name" type="text" value="${esc(this._config.name||'')}"></div><div class="row"><label for="mode">Default view</label><select id="mode"><option value="detailed" ${this._config.mode==='detailed'?'selected':''}>Detailed</option><option value="compact" ${this._config.mode==='compact'?'selected':''}>Compact</option></select></div><div class="row toggle"><input id="forecast" type="checkbox" style="width:auto" ${this._config.show_forecast!==false?'checked':''}><label for="forecast">Show forecast</label></div>`;
    this.shadowRoot.querySelector('#entity').addEventListener('change',e=>this._update({entity:e.target.value}));this.shadowRoot.querySelector('#name').addEventListener('change',e=>this._update({name:e.target.value}));this.shadowRoot.querySelector('#mode').addEventListener('change',e=>this._update({mode:e.target.value}));this.shadowRoot.querySelector('#forecast').addEventListener('change',e=>this._update({show_forecast:e.target.checked}));
  }
}
if(!customElements.get(CARD_TAG))customElements.define(CARD_TAG,GismeteoHACard);
if(!customElements.get(EDITOR_TAG))customElements.define(EDITOR_TAG,GismeteoHAEditor);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type===CARD_TAG))window.customCards.push({type:CARD_TAG,name:'Gismeteo HA Weather',description:'Beautiful weather card, detailed and compact views, hourly and daily forecasts',preview:true,documentationURL:'https://github.com/khaisilk1910/gismeteo_ha'});
