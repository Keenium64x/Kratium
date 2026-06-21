var A=Object.defineProperty,$=Object.defineProperties;var L=Object.getOwnPropertyDescriptors;var i=Object.getOwnPropertySymbols;var g=Object.prototype.hasOwnProperty,k=Object.prototype.propertyIsEnumerable;var m=(t,e,o)=>e in t?A(t,e,{enumerable:!0,configurable:!0,writable:!0,value:o}):t[e]=o,s=(t,e)=>{for(var o in e||(e={}))g.call(e,o)&&m(t,o,e[o]);if(i)for(var o of i(e))k.call(e,o)&&m(t,o,e[o]);return t},l=(t,e)=>$(t,L(e));var C=(t,e)=>{var o={};for(var r in t)g.call(t,r)&&e.indexOf(r)<0&&(o[r]=t[r]);if(t!=null&&i)for(var r of i(t))e.indexOf(r)<0&&k.call(t,r)&&(o[r]=t[r]);return o};import{au as u}from"./index-BVLU-Veg.js";/**
 * @license lucide-vue-next v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const f=t=>t.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase(),P=t=>t.replace(/^([A-Z])|[\s-_]+(\w)/g,(e,o,r)=>r?r.toUpperCase():o.toLowerCase()),j=t=>{const e=P(t);return e.charAt(0).toUpperCase()+e.slice(1)},B=(...t)=>t.filter((e,o,r)=>!!e&&e.trim()!==""&&r.indexOf(e)===o).join(" ").trim(),v=t=>t==="";/**
 * @license lucide-vue-next v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var c={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=(U,{slots:w})=>{var p=U,{name:t,iconNode:e,absoluteStrokeWidth:o,"absolute-stroke-width":r,strokeWidth:n,"stroke-width":d,size:a=c.width,color:x=c.stroke}=p,h=C(p,["name","iconNode","absoluteStrokeWidth","absolute-stroke-width","strokeWidth","stroke-width","size","color"]);return u("svg",l(s(s({},c),h),{width:a,height:a,stroke:x,"stroke-width":v(o)||v(r)||o===!0||r===!0?Number(n||d||c["stroke-width"])*24/Number(a):n||d||c["stroke-width"],class:B("lucide",h.class,...t?[`lucide-${f(j(t))}-icon`,`lucide-${f(t)}`]:["lucide-icon"])}),[...e.map(y=>u(...y)),...w.default?[w.default()]:[]])};/**
 * @license lucide-vue-next v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=(t,e)=>(o,{slots:r,attrs:n})=>u(I,l(s(s({},n),o),{iconNode:e,name:t}),r);/**
 * @license lucide-vue-next v0.562.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const O=M("plus",[["path",{d:"M5 12h14",key:"1ays0h"}],["path",{d:"M12 5v14",key:"s699le"}]]);export{O as P,M as c};
//# sourceMappingURL=plus-QfsLf19B.js.map
