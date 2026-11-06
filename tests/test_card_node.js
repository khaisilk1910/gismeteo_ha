/* Smoke-test custom card registration, weather values and two views with Node. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const registry = new Map();
class HTMLElement {
  constructor() { this.isConnected=true; this.shadowRoot=null; }
  attachShadow(){return this.shadowRoot={innerHTML:'',querySelectorAll:()=>[],querySelector:()=>null};}
}
const ctx={window:{},document:{createElement:name=>new(registry.get(name))()},HTMLElement,
  customElements:{define:(k,v)=>registry.set(k,v),get:k=>registry.get(k)},
  CustomEvent:class{},Date,Promise,Number,Object,String,Array,Math,console,queueMicrotask};
vm.runInNewContext(fs.readFileSync('custom_components/gismeteo_ha/frontend/gismeteo-ha-card.js','utf8'),ctx);
assert(registry.has('gismeteo-ha-card'));
assert(registry.has('gismeteo-ha-card-editor'));
assert.equal(ctx.window.customCards.length,1);
const Card=registry.get('gismeteo-ha-card');
const forecasts={hourly:[{datetime:'2026-11-05T00:00:00+00:00',temperature:30,condition:'sunny'}],daily:[]};
const hass={language:'vi',config:{time_zone:'Asia/Ho_Chi_Minh'},states:{'weather.home':{state:'sunny',last_updated:'2026-11-05T08:29:03+00:00',attributes:{temperature:30,humidity:70,visibility:12,visibility_unit:'km',friendly_name:'Hà Nội'}}},connection:{subscribeMessage(callback,opts){callback({forecast:forecasts[opts.forecast_type]});return Promise.resolve(()=>{});}}};
const card=new Card();card.setConfig({entity:'weather.home',mode:'detailed'});card.hass=hass;card.connectedCallback();
assert(card.shadowRoot.innerHTML.includes('Hà Nội'));
assert(card.shadowRoot.innerHTML.includes('Tầm nhìn'));
assert(card.shadowRoot.innerHTML.includes('12 km'));
assert(card.shadowRoot.innerHTML.includes('Theo giờ'));
assert(card.shadowRoot.innerHTML.includes('Gismeteo'));
assert(card.shadowRoot.innerHTML.includes('07:00')); // Forecast timezone: UTC 00:00 => HA 07:00
assert(card.shadowRoot.innerHTML.includes('15:29')); // Update timestamp in HA time zone
card.setConfig({entity:'weather.home',mode:'compact'});
assert(card.shadowRoot.innerHTML.includes('class="compact'));
assert(!card.shadowRoot.innerHTML.includes('class="forecast-list"'));
card.disconnectedCallback();
console.log('Card smoke test: passed');
