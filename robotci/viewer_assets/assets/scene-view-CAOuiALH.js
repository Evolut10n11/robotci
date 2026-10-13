import{C as Dt,V as g,M as B,T as I,Q as at,S as rt,a as R,R as Tt,P as At,b as bt,I as Lt,F as ht,e as st,f as N,W as zt,B as $,g as wt,h as Ot,i as V,U as St,j as q,k as Y,l as F,L as Rt,m as Ct,o as xt,G as Ut,p as jt,O as kt,q as vt,r as It,s as Nt,t as Bt,u as Wt,v as Ht,w as lt,A as Yt,x as Ft,y as Zt,H as Gt,D as ct,z as Kt,E as Xt,J as Vt,K as qt,N as dt,X as $t,Y as Qt,Z as Jt,_ as te,$ as ee}from"./description-model-JjarLS_Z.js";import{t as ie,a as se,C as Q,p as ne}from"./index-CYK0i028.js";const pt={type:"change"},nt={type:"start"},Et={type:"end"},Z=new Tt,ut=new At,oe=Math.cos(70*bt.DEG2RAD),M=new g,L=2*Math.PI,v={NONE:-1,ROTATE:0,DOLLY:1,PAN:2,TOUCH_ROTATE:3,TOUCH_PAN:4,TOUCH_DOLLY_PAN:5,TOUCH_DOLLY_ROTATE:6},J=1e-6;class ae extends Dt{constructor(t,e=null){super(t,e),this.state=v.NONE,this.target=new g,this.cursor=new g,this.minDistance=0,this.maxDistance=1/0,this.minZoom=0,this.maxZoom=1/0,this.minTargetRadius=0,this.maxTargetRadius=1/0,this.minPolarAngle=0,this.maxPolarAngle=Math.PI,this.minAzimuthAngle=-1/0,this.maxAzimuthAngle=1/0,this.enableDamping=!1,this.dampingFactor=.05,this.enableZoom=!0,this.zoomSpeed=1,this.enableRotate=!0,this.rotateSpeed=1,this.keyRotateSpeed=1,this.enablePan=!0,this.panSpeed=1,this.screenSpacePanning=!0,this.keyPanSpeed=7,this.zoomToCursor=!1,this.autoRotate=!1,this.autoRotateSpeed=2,this.keys={LEFT:"ArrowLeft",UP:"ArrowUp",RIGHT:"ArrowRight",BOTTOM:"ArrowDown"},this.mouseButtons={LEFT:B.ROTATE,MIDDLE:B.DOLLY,RIGHT:B.PAN},this.touches={ONE:I.ROTATE,TWO:I.DOLLY_PAN},this.target0=this.target.clone(),this.position0=this.object.position.clone(),this.zoom0=this.object.zoom,this._domElementKeyEvents=null,this._lastPosition=new g,this._lastQuaternion=new at,this._lastTargetPosition=new g,this._quat=new at().setFromUnitVectors(t.up,new g(0,1,0)),this._quatInverse=this._quat.clone().invert(),this._spherical=new rt,this._sphericalDelta=new rt,this._scale=1,this._panOffset=new g,this._rotateStart=new R,this._rotateEnd=new R,this._rotateDelta=new R,this._panStart=new R,this._panEnd=new R,this._panDelta=new R,this._dollyStart=new R,this._dollyEnd=new R,this._dollyDelta=new R,this._dollyDirection=new g,this._mouse=new R,this._performCursorZoom=!1,this._pointers=[],this._pointerPositions={},this._controlActive=!1,this._onPointerMove=he.bind(this),this._onPointerDown=re.bind(this),this._onPointerUp=le.bind(this),this._onContextMenu=_e.bind(this),this._onMouseWheel=pe.bind(this),this._onKeyDown=ue.bind(this),this._onTouchStart=fe.bind(this),this._onTouchMove=me.bind(this),this._onMouseDown=ce.bind(this),this._onMouseMove=de.bind(this),this._interceptControlDown=ye.bind(this),this._interceptControlUp=ge.bind(this),this.domElement!==null&&this.connect(this.domElement),this.update()}connect(t){super.connect(t),this.domElement.addEventListener("pointerdown",this._onPointerDown),this.domElement.addEventListener("pointercancel",this._onPointerUp),this.domElement.addEventListener("contextmenu",this._onContextMenu),this.domElement.addEventListener("wheel",this._onMouseWheel,{passive:!1}),this.domElement.getRootNode().addEventListener("keydown",this._interceptControlDown,{passive:!0,capture:!0}),this.domElement.style.touchAction="none"}disconnect(){this.domElement.removeEventListener("pointerdown",this._onPointerDown),this.domElement.removeEventListener("pointermove",this._onPointerMove),this.domElement.removeEventListener("pointerup",this._onPointerUp),this.domElement.removeEventListener("pointercancel",this._onPointerUp),this.domElement.removeEventListener("wheel",this._onMouseWheel),this.domElement.removeEventListener("contextmenu",this._onContextMenu),this.stopListenToKeyEvents(),this.domElement.getRootNode().removeEventListener("keydown",this._interceptControlDown,{capture:!0}),this.domElement.style.touchAction="auto"}dispose(){this.disconnect()}getPolarAngle(){return this._spherical.phi}getAzimuthalAngle(){return this._spherical.theta}getDistance(){return this.object.position.distanceTo(this.target)}listenToKeyEvents(t){t.addEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=t}stopListenToKeyEvents(){this._domElementKeyEvents!==null&&(this._domElementKeyEvents.removeEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=null)}saveState(){this.target0.copy(this.target),this.position0.copy(this.object.position),this.zoom0=this.object.zoom}reset(){this.target.copy(this.target0),this.object.position.copy(this.position0),this.object.zoom=this.zoom0,this.object.updateProjectionMatrix(),this.dispatchEvent(pt),this.update(),this.state=v.NONE}update(t=null){const e=this.object.position;M.copy(e).sub(this.target),M.applyQuaternion(this._quat),this._spherical.setFromVector3(M),this.autoRotate&&this.state===v.NONE&&this._rotateLeft(this._getAutoRotationAngle(t)),this.enableDamping?(this._spherical.theta+=this._sphericalDelta.theta*this.dampingFactor,this._spherical.phi+=this._sphericalDelta.phi*this.dampingFactor):(this._spherical.theta+=this._sphericalDelta.theta,this._spherical.phi+=this._sphericalDelta.phi);let i=this.minAzimuthAngle,s=this.maxAzimuthAngle;isFinite(i)&&isFinite(s)&&(i<-Math.PI?i+=L:i>Math.PI&&(i-=L),s<-Math.PI?s+=L:s>Math.PI&&(s-=L),i<=s?this._spherical.theta=Math.max(i,Math.min(s,this._spherical.theta)):this._spherical.theta=this._spherical.theta>(i+s)/2?Math.max(i,this._spherical.theta):Math.min(s,this._spherical.theta)),this._spherical.phi=Math.max(this.minPolarAngle,Math.min(this.maxPolarAngle,this._spherical.phi)),this._spherical.makeSafe(),this.enableDamping===!0?this.target.addScaledVector(this._panOffset,this.dampingFactor):this.target.add(this._panOffset),this.target.sub(this.cursor),this.target.clampLength(this.minTargetRadius,this.maxTargetRadius),this.target.add(this.cursor);let n=!1;if(this.zoomToCursor&&this._performCursorZoom||this.object.isOrthographicCamera)this._spherical.radius=this._clampDistance(this._spherical.radius);else{const r=this._spherical.radius;this._spherical.radius=this._clampDistance(this._spherical.radius*this._scale),n=r!=this._spherical.radius}if(M.setFromSpherical(this._spherical),M.applyQuaternion(this._quatInverse),e.copy(this.target).add(M),this.object.lookAt(this.target),this.enableDamping===!0?(this._sphericalDelta.theta*=1-this.dampingFactor,this._sphericalDelta.phi*=1-this.dampingFactor,this._panOffset.multiplyScalar(1-this.dampingFactor)):(this._sphericalDelta.set(0,0,0),this._panOffset.set(0,0,0)),this.zoomToCursor&&this._performCursorZoom){let r=null;if(this.object.isPerspectiveCamera){const u=M.length();r=this._clampDistance(u*this._scale);const m=u-r;this.object.position.addScaledVector(this._dollyDirection,m),this.object.updateMatrixWorld(),n=!!m}else if(this.object.isOrthographicCamera){const u=new g(this._mouse.x,this._mouse.y,0);u.unproject(this.object);const m=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),this.object.updateProjectionMatrix(),n=m!==this.object.zoom;const f=new g(this._mouse.x,this._mouse.y,0);f.unproject(this.object),this.object.position.sub(f).add(u),this.object.updateMatrixWorld(),r=M.length()}else console.warn("WARNING: OrbitControls.js encountered an unknown camera type - zoom to cursor disabled."),this.zoomToCursor=!1;r!==null&&(this.screenSpacePanning?this.target.set(0,0,-1).transformDirection(this.object.matrix).multiplyScalar(r).add(this.object.position):(Z.origin.copy(this.object.position),Z.direction.set(0,0,-1).transformDirection(this.object.matrix),Math.abs(this.object.up.dot(Z.direction))<oe?this.object.lookAt(this.target):(ut.setFromNormalAndCoplanarPoint(this.object.up,this.target),Z.intersectPlane(ut,this.target))))}else if(this.object.isOrthographicCamera){const r=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),r!==this.object.zoom&&(this.object.updateProjectionMatrix(),n=!0)}return this._scale=1,this._performCursorZoom=!1,n||this._lastPosition.distanceToSquared(this.object.position)>J||8*(1-this._lastQuaternion.dot(this.object.quaternion))>J||this._lastTargetPosition.distanceToSquared(this.target)>J?(this.dispatchEvent(pt),this._lastPosition.copy(this.object.position),this._lastQuaternion.copy(this.object.quaternion),this._lastTargetPosition.copy(this.target),!0):!1}_getAutoRotationAngle(t){return t!==null?L/60*this.autoRotateSpeed*t:L/60/60*this.autoRotateSpeed}_getZoomScale(t){const e=Math.abs(t*.01);return Math.pow(.95,this.zoomSpeed*e)}_rotateLeft(t){this._sphericalDelta.theta-=t}_rotateUp(t){this._sphericalDelta.phi-=t}_panLeft(t,e){M.setFromMatrixColumn(e,0),M.multiplyScalar(-t),this._panOffset.add(M)}_panUp(t,e){this.screenSpacePanning===!0?M.setFromMatrixColumn(e,1):(M.setFromMatrixColumn(e,0),M.crossVectors(this.object.up,M)),M.multiplyScalar(t),this._panOffset.add(M)}_pan(t,e){const i=this.domElement;if(this.object.isPerspectiveCamera){const s=this.object.position;M.copy(s).sub(this.target);let n=M.length();n*=Math.tan(this.object.fov/2*Math.PI/180),this._panLeft(2*t*n/i.clientHeight,this.object.matrix),this._panUp(2*e*n/i.clientHeight,this.object.matrix)}else this.object.isOrthographicCamera?(this._panLeft(t*(this.object.right-this.object.left)/this.object.zoom/i.clientWidth,this.object.matrix),this._panUp(e*(this.object.top-this.object.bottom)/this.object.zoom/i.clientHeight,this.object.matrix)):(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - pan disabled."),this.enablePan=!1)}_dollyOut(t){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale/=t:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_dollyIn(t){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale*=t:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_updateZoomParameters(t,e){if(!this.zoomToCursor)return;this._performCursorZoom=!0;const i=this.domElement.getBoundingClientRect(),s=t-i.left,n=e-i.top,r=i.width,u=i.height;this._mouse.x=s/r*2-1,this._mouse.y=-(n/u)*2+1,this._dollyDirection.set(this._mouse.x,this._mouse.y,1).unproject(this.object).sub(this.object.position).normalize()}_clampDistance(t){return Math.max(this.minDistance,Math.min(this.maxDistance,t))}_handleMouseDownRotate(t){this._rotateStart.set(t.clientX,t.clientY)}_handleMouseDownDolly(t){this._updateZoomParameters(t.clientX,t.clientX),this._dollyStart.set(t.clientX,t.clientY)}_handleMouseDownPan(t){this._panStart.set(t.clientX,t.clientY)}_handleMouseMoveRotate(t){this._rotateEnd.set(t.clientX,t.clientY),this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);const e=this.domElement;this._rotateLeft(L*this._rotateDelta.x/e.clientHeight),this._rotateUp(L*this._rotateDelta.y/e.clientHeight),this._rotateStart.copy(this._rotateEnd),this.update()}_handleMouseMoveDolly(t){this._dollyEnd.set(t.clientX,t.clientY),this._dollyDelta.subVectors(this._dollyEnd,this._dollyStart),this._dollyDelta.y>0?this._dollyOut(this._getZoomScale(this._dollyDelta.y)):this._dollyDelta.y<0&&this._dollyIn(this._getZoomScale(this._dollyDelta.y)),this._dollyStart.copy(this._dollyEnd),this.update()}_handleMouseMovePan(t){this._panEnd.set(t.clientX,t.clientY),this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd),this.update()}_handleMouseWheel(t){this._updateZoomParameters(t.clientX,t.clientY),t.deltaY<0?this._dollyIn(this._getZoomScale(t.deltaY)):t.deltaY>0&&this._dollyOut(this._getZoomScale(t.deltaY)),this.update()}_handleKeyDown(t){let e=!1;switch(t.code){case this.keys.UP:t.ctrlKey||t.metaKey||t.shiftKey?this.enableRotate&&this._rotateUp(L*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,this.keyPanSpeed),e=!0;break;case this.keys.BOTTOM:t.ctrlKey||t.metaKey||t.shiftKey?this.enableRotate&&this._rotateUp(-L*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(0,-this.keyPanSpeed),e=!0;break;case this.keys.LEFT:t.ctrlKey||t.metaKey||t.shiftKey?this.enableRotate&&this._rotateLeft(L*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(this.keyPanSpeed,0),e=!0;break;case this.keys.RIGHT:t.ctrlKey||t.metaKey||t.shiftKey?this.enableRotate&&this._rotateLeft(-L*this.keyRotateSpeed/this.domElement.clientHeight):this.enablePan&&this._pan(-this.keyPanSpeed,0),e=!0;break}e&&(t.preventDefault(),this.update())}_handleTouchStartRotate(t){if(this._pointers.length===1)this._rotateStart.set(t.pageX,t.pageY);else{const e=this._getSecondPointerPosition(t),i=.5*(t.pageX+e.x),s=.5*(t.pageY+e.y);this._rotateStart.set(i,s)}}_handleTouchStartPan(t){if(this._pointers.length===1)this._panStart.set(t.pageX,t.pageY);else{const e=this._getSecondPointerPosition(t),i=.5*(t.pageX+e.x),s=.5*(t.pageY+e.y);this._panStart.set(i,s)}}_handleTouchStartDolly(t){const e=this._getSecondPointerPosition(t),i=t.pageX-e.x,s=t.pageY-e.y,n=Math.sqrt(i*i+s*s);this._dollyStart.set(0,n)}_handleTouchStartDollyPan(t){this.enableZoom&&this._handleTouchStartDolly(t),this.enablePan&&this._handleTouchStartPan(t)}_handleTouchStartDollyRotate(t){this.enableZoom&&this._handleTouchStartDolly(t),this.enableRotate&&this._handleTouchStartRotate(t)}_handleTouchMoveRotate(t){if(this._pointers.length==1)this._rotateEnd.set(t.pageX,t.pageY);else{const i=this._getSecondPointerPosition(t),s=.5*(t.pageX+i.x),n=.5*(t.pageY+i.y);this._rotateEnd.set(s,n)}this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);const e=this.domElement;this._rotateLeft(L*this._rotateDelta.x/e.clientHeight),this._rotateUp(L*this._rotateDelta.y/e.clientHeight),this._rotateStart.copy(this._rotateEnd)}_handleTouchMovePan(t){if(this._pointers.length===1)this._panEnd.set(t.pageX,t.pageY);else{const e=this._getSecondPointerPosition(t),i=.5*(t.pageX+e.x),s=.5*(t.pageY+e.y);this._panEnd.set(i,s)}this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd)}_handleTouchMoveDolly(t){const e=this._getSecondPointerPosition(t),i=t.pageX-e.x,s=t.pageY-e.y,n=Math.sqrt(i*i+s*s);this._dollyEnd.set(0,n),this._dollyDelta.set(0,Math.pow(this._dollyEnd.y/this._dollyStart.y,this.zoomSpeed)),this._dollyOut(this._dollyDelta.y),this._dollyStart.copy(this._dollyEnd);const r=(t.pageX+e.x)*.5,u=(t.pageY+e.y)*.5;this._updateZoomParameters(r,u)}_handleTouchMoveDollyPan(t){this.enableZoom&&this._handleTouchMoveDolly(t),this.enablePan&&this._handleTouchMovePan(t)}_handleTouchMoveDollyRotate(t){this.enableZoom&&this._handleTouchMoveDolly(t),this.enableRotate&&this._handleTouchMoveRotate(t)}_addPointer(t){this._pointers.push(t.pointerId)}_removePointer(t){delete this._pointerPositions[t.pointerId];for(let e=0;e<this._pointers.length;e++)if(this._pointers[e]==t.pointerId){this._pointers.splice(e,1);return}}_isTrackingPointer(t){for(let e=0;e<this._pointers.length;e++)if(this._pointers[e]==t.pointerId)return!0;return!1}_trackPointer(t){let e=this._pointerPositions[t.pointerId];e===void 0&&(e=new R,this._pointerPositions[t.pointerId]=e),e.set(t.pageX,t.pageY)}_getSecondPointerPosition(t){const e=t.pointerId===this._pointers[0]?this._pointers[1]:this._pointers[0];return this._pointerPositions[e]}_customWheelEvent(t){const e=t.deltaMode,i={clientX:t.clientX,clientY:t.clientY,deltaY:t.deltaY};switch(e){case 1:i.deltaY*=16;break;case 2:i.deltaY*=100;break}return t.ctrlKey&&!this._controlActive&&(i.deltaY*=10),i}}function re(a){this.enabled!==!1&&(this._pointers.length===0&&(this.domElement.setPointerCapture(a.pointerId),this.domElement.addEventListener("pointermove",this._onPointerMove),this.domElement.addEventListener("pointerup",this._onPointerUp)),!this._isTrackingPointer(a)&&(this._addPointer(a),a.pointerType==="touch"?this._onTouchStart(a):this._onMouseDown(a)))}function he(a){this.enabled!==!1&&(a.pointerType==="touch"?this._onTouchMove(a):this._onMouseMove(a))}function le(a){switch(this._removePointer(a),this._pointers.length){case 0:this.domElement.releasePointerCapture(a.pointerId),this.domElement.removeEventListener("pointermove",this._onPointerMove),this.domElement.removeEventListener("pointerup",this._onPointerUp),this.dispatchEvent(Et),this.state=v.NONE;break;case 1:const t=this._pointers[0],e=this._pointerPositions[t];this._onTouchStart({pointerId:t,pageX:e.x,pageY:e.y});break}}function ce(a){let t;switch(a.button){case 0:t=this.mouseButtons.LEFT;break;case 1:t=this.mouseButtons.MIDDLE;break;case 2:t=this.mouseButtons.RIGHT;break;default:t=-1}switch(t){case B.DOLLY:if(this.enableZoom===!1)return;this._handleMouseDownDolly(a),this.state=v.DOLLY;break;case B.ROTATE:if(a.ctrlKey||a.metaKey||a.shiftKey){if(this.enablePan===!1)return;this._handleMouseDownPan(a),this.state=v.PAN}else{if(this.enableRotate===!1)return;this._handleMouseDownRotate(a),this.state=v.ROTATE}break;case B.PAN:if(a.ctrlKey||a.metaKey||a.shiftKey){if(this.enableRotate===!1)return;this._handleMouseDownRotate(a),this.state=v.ROTATE}else{if(this.enablePan===!1)return;this._handleMouseDownPan(a),this.state=v.PAN}break;default:this.state=v.NONE}this.state!==v.NONE&&this.dispatchEvent(nt)}function de(a){switch(this.state){case v.ROTATE:if(this.enableRotate===!1)return;this._handleMouseMoveRotate(a);break;case v.DOLLY:if(this.enableZoom===!1)return;this._handleMouseMoveDolly(a);break;case v.PAN:if(this.enablePan===!1)return;this._handleMouseMovePan(a);break}}function pe(a){this.enabled===!1||this.enableZoom===!1||this.state!==v.NONE||(a.preventDefault(),this.dispatchEvent(nt),this._handleMouseWheel(this._customWheelEvent(a)),this.dispatchEvent(Et))}function ue(a){this.enabled!==!1&&this._handleKeyDown(a)}function fe(a){switch(this._trackPointer(a),this._pointers.length){case 1:switch(this.touches.ONE){case I.ROTATE:if(this.enableRotate===!1)return;this._handleTouchStartRotate(a),this.state=v.TOUCH_ROTATE;break;case I.PAN:if(this.enablePan===!1)return;this._handleTouchStartPan(a),this.state=v.TOUCH_PAN;break;default:this.state=v.NONE}break;case 2:switch(this.touches.TWO){case I.DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchStartDollyPan(a),this.state=v.TOUCH_DOLLY_PAN;break;case I.DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchStartDollyRotate(a),this.state=v.TOUCH_DOLLY_ROTATE;break;default:this.state=v.NONE}break;default:this.state=v.NONE}this.state!==v.NONE&&this.dispatchEvent(nt)}function me(a){switch(this._trackPointer(a),this.state){case v.TOUCH_ROTATE:if(this.enableRotate===!1)return;this._handleTouchMoveRotate(a),this.update();break;case v.TOUCH_PAN:if(this.enablePan===!1)return;this._handleTouchMovePan(a),this.update();break;case v.TOUCH_DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchMoveDollyPan(a),this.update();break;case v.TOUCH_DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchMoveDollyRotate(a),this.update();break;default:this.state=v.NONE}}function _e(a){this.enabled!==!1&&a.preventDefault()}function ye(a){a.key==="Control"&&(this._controlActive=!0,this.domElement.getRootNode().addEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}function ge(a){a.key==="Control"&&(this._controlActive=!1,this.domElement.getRootNode().removeEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}const ft=new $,G=new g;class Mt extends Lt{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type="LineSegmentsGeometry";const t=[-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],e=[-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],i=[0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5];this.setIndex(i),this.setAttribute("position",new ht(t,3)),this.setAttribute("uv",new ht(e,2))}applyMatrix4(t){const e=this.attributes.instanceStart,i=this.attributes.instanceEnd;return e!==void 0&&(e.applyMatrix4(t),i.applyMatrix4(t),e.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(t){let e;t instanceof Float32Array?e=t:Array.isArray(t)&&(e=new Float32Array(t));const i=new st(e,6,1);return this.setAttribute("instanceStart",new N(i,3,0)),this.setAttribute("instanceEnd",new N(i,3,3)),this.instanceCount=this.attributes.instanceStart.count,this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(t){let e;t instanceof Float32Array?e=t:Array.isArray(t)&&(e=new Float32Array(t));const i=new st(e,6,1);return this.setAttribute("instanceColorStart",new N(i,3,0)),this.setAttribute("instanceColorEnd",new N(i,3,3)),this}fromWireframeGeometry(t){return this.setPositions(t.attributes.position.array),this}fromEdgesGeometry(t){return this.setPositions(t.attributes.position.array),this}fromMesh(t){return this.fromWireframeGeometry(new zt(t.geometry)),this}fromLineSegments(t){const e=t.geometry;return this.setPositions(e.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new $);const t=this.attributes.instanceStart,e=this.attributes.instanceEnd;t!==void 0&&e!==void 0&&(this.boundingBox.setFromBufferAttribute(t),ft.setFromBufferAttribute(e),this.boundingBox.union(ft))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new wt),this.boundingBox===null&&this.computeBoundingBox();const t=this.attributes.instanceStart,e=this.attributes.instanceEnd;if(t!==void 0&&e!==void 0){const i=this.boundingSphere.center;this.boundingBox.getCenter(i);let s=0;for(let n=0,r=t.count;n<r;n++)G.fromBufferAttribute(t,n),s=Math.max(s,i.distanceToSquared(G)),G.fromBufferAttribute(e,n),s=Math.max(s,i.distanceToSquared(G));this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&console.error("THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.",this)}}toJSON(){}}q.line={worldUnits:{value:1},linewidth:{value:1},resolution:{value:new R(1,1)},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}};V.line={uniforms:St.merge([q.common,q.fog,q.line]),vertexShader:`
		#include <common>
		#include <color_pars_vertex>
		#include <fog_pars_vertex>
		#include <logdepthbuf_pars_vertex>
		#include <clipping_planes_pars_vertex>

		uniform float linewidth;
		uniform vec2 resolution;

		attribute vec3 instanceStart;
		attribute vec3 instanceEnd;

		attribute vec3 instanceColorStart;
		attribute vec3 instanceColorEnd;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#ifdef USE_DASH

			uniform float dashScale;
			attribute float instanceDistanceStart;
			attribute float instanceDistanceEnd;
			varying float vLineDistance;

		#endif

		void trimSegment( const in vec4 start, inout vec4 end ) {

			// trim end segment so it terminates between the camera plane and the near plane

			// conservative estimate of the near plane
			float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
			float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column
			float nearEstimate = - 0.5 * b / a;

			float alpha = ( nearEstimate - start.z ) / ( end.z - start.z );

			end.xyz = mix( start.xyz, end.xyz, alpha );

		}

		void main() {

			#ifdef USE_COLOR

				vColor.xyz = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

			#endif

			#ifdef USE_DASH

				vLineDistance = ( position.y < 0.5 ) ? dashScale * instanceDistanceStart : dashScale * instanceDistanceEnd;
				vUv = uv;

			#endif

			float aspect = resolution.x / resolution.y;

			// camera space
			vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
			vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

			#ifdef WORLD_UNITS

				worldStart = start.xyz;
				worldEnd = end.xyz;

			#else

				vUv = uv;

			#endif

			// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
			// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
			// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
			// perhaps there is a more elegant solution -- WestLangley

			bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

			if ( perspective ) {

				if ( start.z < 0.0 && end.z >= 0.0 ) {

					trimSegment( start, end );

				} else if ( end.z < 0.0 && start.z >= 0.0 ) {

					trimSegment( end, start );

				}

			}

			// clip space
			vec4 clipStart = projectionMatrix * start;
			vec4 clipEnd = projectionMatrix * end;

			// ndc space
			vec3 ndcStart = clipStart.xyz / clipStart.w;
			vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

			// direction
			vec2 dir = ndcEnd.xy - ndcStart.xy;

			// account for clip-space aspect ratio
			dir.x *= aspect;
			dir = normalize( dir );

			#ifdef WORLD_UNITS

				vec3 worldDir = normalize( end.xyz - start.xyz );
				vec3 tmpFwd = normalize( mix( start.xyz, end.xyz, 0.5 ) );
				vec3 worldUp = normalize( cross( worldDir, tmpFwd ) );
				vec3 worldFwd = cross( worldDir, worldUp );
				worldPos = position.y < 0.5 ? start: end;

				// height offset
				float hw = linewidth * 0.5;
				worldPos.xyz += position.x < 0.0 ? hw * worldUp : - hw * worldUp;

				// don't extend the line if we're rendering dashes because we
				// won't be rendering the endcaps
				#ifndef USE_DASH

					// cap extension
					worldPos.xyz += position.y < 0.5 ? - hw * worldDir : hw * worldDir;

					// add width to the box
					worldPos.xyz += worldFwd * hw;

					// endcaps
					if ( position.y > 1.0 || position.y < 0.0 ) {

						worldPos.xyz -= worldFwd * 2.0 * hw;

					}

				#endif

				// project the worldpos
				vec4 clip = projectionMatrix * worldPos;

				// shift the depth of the projected points so the line
				// segments overlap neatly
				vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
				clip.z = clipPose.z * clip.w;

			#else

				vec2 offset = vec2( dir.y, - dir.x );
				// undo aspect ratio adjustment
				dir.x /= aspect;
				offset.x /= aspect;

				// sign flip
				if ( position.x < 0.0 ) offset *= - 1.0;

				// endcaps
				if ( position.y < 0.0 ) {

					offset += - dir;

				} else if ( position.y > 1.0 ) {

					offset += dir;

				}

				// adjust for linewidth
				offset *= linewidth;

				// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
				offset /= resolution.y;

				// select end
				vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

				// back to clip space
				offset *= clip.w;

				clip.xy += offset;

			#endif

			gl_Position = clip;

			vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

			#include <logdepthbuf_vertex>
			#include <clipping_planes_vertex>
			#include <fog_vertex>

		}
		`,fragmentShader:`
		uniform vec3 diffuse;
		uniform float opacity;
		uniform float linewidth;

		#ifdef USE_DASH

			uniform float dashOffset;
			uniform float dashSize;
			uniform float gapSize;

		#endif

		varying float vLineDistance;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#include <common>
		#include <color_pars_fragment>
		#include <fog_pars_fragment>
		#include <logdepthbuf_pars_fragment>
		#include <clipping_planes_pars_fragment>

		vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

			float mua;
			float mub;

			vec3 p13 = p1 - p3;
			vec3 p43 = p4 - p3;

			vec3 p21 = p2 - p1;

			float d1343 = dot( p13, p43 );
			float d4321 = dot( p43, p21 );
			float d1321 = dot( p13, p21 );
			float d4343 = dot( p43, p43 );
			float d2121 = dot( p21, p21 );

			float denom = d2121 * d4343 - d4321 * d4321;

			float numer = d1343 * d4321 - d1321 * d4343;

			mua = numer / denom;
			mua = clamp( mua, 0.0, 1.0 );
			mub = ( d1343 + d4321 * ( mua ) ) / d4343;
			mub = clamp( mub, 0.0, 1.0 );

			return vec2( mua, mub );

		}

		void main() {

			float alpha = opacity;
			vec4 diffuseColor = vec4( diffuse, alpha );

			#include <clipping_planes_fragment>

			#ifdef USE_DASH

				if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

				if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

			#endif

			#ifdef WORLD_UNITS

				// Find the closest points on the view ray and the line segment
				vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
				vec3 lineDir = worldEnd - worldStart;
				vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

				vec3 p1 = worldStart + lineDir * params.x;
				vec3 p2 = rayEnd * params.y;
				vec3 delta = p1 - p2;
				float len = length( delta );
				float norm = len / linewidth;

				#ifndef USE_DASH

					#ifdef USE_ALPHA_TO_COVERAGE

						float dnorm = fwidth( norm );
						alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

					#else

						if ( norm > 0.5 ) {

							discard;

						}

					#endif

				#endif

			#else

				#ifdef USE_ALPHA_TO_COVERAGE

					// artifacts appear on some hardware if a derivative is taken within a conditional
					float a = vUv.x;
					float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
					float len2 = a * a + b * b;
					float dlen = fwidth( len2 );

					if ( abs( vUv.y ) > 1.0 ) {

						alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

					}

				#else

					if ( abs( vUv.y ) > 1.0 ) {

						float a = vUv.x;
						float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
						float len2 = a * a + b * b;

						if ( len2 > 1.0 ) discard;

					}

				#endif

			#endif

			#include <logdepthbuf_fragment>
			#include <color_fragment>

			gl_FragColor = vec4( diffuseColor.rgb, alpha );

			#include <tonemapping_fragment>
			#include <colorspace_fragment>
			#include <fog_fragment>
			#include <premultiplied_alpha_fragment>

		}
		`};class Pt extends Ot{constructor(t){super({type:"LineMaterial",uniforms:St.clone(V.line.uniforms),vertexShader:V.line.vertexShader,fragmentShader:V.line.fragmentShader,clipping:!0}),this.isLineMaterial=!0,this.setValues(t)}get color(){return this.uniforms.diffuse.value}set color(t){this.uniforms.diffuse.value=t}get worldUnits(){return"WORLD_UNITS"in this.defines}set worldUnits(t){t===!0?this.defines.WORLD_UNITS="":delete this.defines.WORLD_UNITS}get linewidth(){return this.uniforms.linewidth.value}set linewidth(t){this.uniforms.linewidth&&(this.uniforms.linewidth.value=t)}get dashed(){return"USE_DASH"in this.defines}set dashed(t){t===!0!==this.dashed&&(this.needsUpdate=!0),t===!0?this.defines.USE_DASH="":delete this.defines.USE_DASH}get dashScale(){return this.uniforms.dashScale.value}set dashScale(t){this.uniforms.dashScale.value=t}get dashSize(){return this.uniforms.dashSize.value}set dashSize(t){this.uniforms.dashSize.value=t}get dashOffset(){return this.uniforms.dashOffset.value}set dashOffset(t){this.uniforms.dashOffset.value=t}get gapSize(){return this.uniforms.gapSize.value}set gapSize(t){this.uniforms.gapSize.value=t}get opacity(){return this.uniforms.opacity.value}set opacity(t){this.uniforms&&(this.uniforms.opacity.value=t)}get resolution(){return this.uniforms.resolution.value}set resolution(t){this.uniforms.resolution.value.copy(t)}get alphaToCoverage(){return"USE_ALPHA_TO_COVERAGE"in this.defines}set alphaToCoverage(t){this.defines&&(t===!0!==this.alphaToCoverage&&(this.needsUpdate=!0),t===!0?this.defines.USE_ALPHA_TO_COVERAGE="":delete this.defines.USE_ALPHA_TO_COVERAGE)}}const tt=new F,mt=new g,_t=new g,P=new F,D=new F,C=new F,et=new g,it=new Ct,T=new Rt,yt=new g,K=new $,X=new wt,U=new F;let j,k;function gt(a,t,e){return U.set(0,0,-t,1).applyMatrix4(a.projectionMatrix),U.multiplyScalar(1/U.w),U.x=k/e.width,U.y=k/e.height,U.applyMatrix4(a.projectionMatrixInverse),U.multiplyScalar(1/U.w),Math.abs(Math.max(U.x,U.y))}function be(a,t){const e=a.matrixWorld,i=a.geometry,s=i.attributes.instanceStart,n=i.attributes.instanceEnd,r=Math.min(i.instanceCount,s.count);for(let u=0,m=r;u<m;u++){T.start.fromBufferAttribute(s,u),T.end.fromBufferAttribute(n,u),T.applyMatrix4(e);const f=new g,h=new g;j.distanceSqToSegment(T.start,T.end,h,f),h.distanceTo(f)<k*.5&&t.push({point:h,pointOnLine:f,distance:j.origin.distanceTo(h),object:a,face:null,faceIndex:u,uv:null,uv1:null})}}function we(a,t,e){const i=t.projectionMatrix,n=a.material.resolution,r=a.matrixWorld,u=a.geometry,m=u.attributes.instanceStart,f=u.attributes.instanceEnd,h=Math.min(u.instanceCount,m.count),l=-t.near;j.at(1,C),C.w=1,C.applyMatrix4(t.matrixWorldInverse),C.applyMatrix4(i),C.multiplyScalar(1/C.w),C.x*=n.x/2,C.y*=n.y/2,C.z=0,et.copy(C),it.multiplyMatrices(t.matrixWorldInverse,r);for(let b=0,S=h;b<S;b++){if(P.fromBufferAttribute(m,b),D.fromBufferAttribute(f,b),P.w=1,D.w=1,P.applyMatrix4(it),D.applyMatrix4(it),P.z>l&&D.z>l)continue;if(P.z>l){const d=P.z-D.z,_=(P.z-l)/d;P.lerp(D,_)}else if(D.z>l){const d=D.z-P.z,_=(D.z-l)/d;D.lerp(P,_)}P.applyMatrix4(i),D.applyMatrix4(i),P.multiplyScalar(1/P.w),D.multiplyScalar(1/D.w),P.x*=n.x/2,P.y*=n.y/2,D.x*=n.x/2,D.y*=n.y/2,T.start.copy(P),T.start.z=0,T.end.copy(D),T.end.z=0;const w=T.closestPointToPointParameter(et,!0);T.at(w,yt);const A=bt.lerp(P.z,D.z,w),o=A>=-1&&A<=1,c=et.distanceTo(yt)<k*.5;if(o&&c){T.start.fromBufferAttribute(m,b),T.end.fromBufferAttribute(f,b),T.start.applyMatrix4(r),T.end.applyMatrix4(r);const d=new g,_=new g;j.distanceSqToSegment(T.start,T.end,_,d),e.push({point:_,pointOnLine:d,distance:j.origin.distanceTo(_),object:a,face:null,faceIndex:b,uv:null,uv1:null})}}}class Se extends Y{constructor(t=new Mt,e=new Pt({color:Math.random()*16777215})){super(t,e),this.isLineSegments2=!0,this.type="LineSegments2"}computeLineDistances(){const t=this.geometry,e=t.attributes.instanceStart,i=t.attributes.instanceEnd,s=new Float32Array(2*e.count);for(let r=0,u=0,m=e.count;r<m;r++,u+=2)mt.fromBufferAttribute(e,r),_t.fromBufferAttribute(i,r),s[u]=u===0?0:s[u-1],s[u+1]=s[u]+mt.distanceTo(_t);const n=new st(s,2,1);return t.setAttribute("instanceDistanceStart",new N(n,1,0)),t.setAttribute("instanceDistanceEnd",new N(n,1,1)),this}raycast(t,e){const i=this.material.worldUnits,s=t.camera;s===null&&!i&&console.error('LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.');const n=t.params.Line2!==void 0&&t.params.Line2.threshold||0;j=t.ray;const r=this.matrixWorld,u=this.geometry,m=this.material;k=m.linewidth+n,u.boundingSphere===null&&u.computeBoundingSphere(),X.copy(u.boundingSphere).applyMatrix4(r);let f;if(i)f=k*.5;else{const l=Math.max(s.near,X.distanceToPoint(j.origin));f=gt(s,l,m.resolution)}if(X.radius+=f,j.intersectsSphere(X)===!1)return;u.boundingBox===null&&u.computeBoundingBox(),K.copy(u.boundingBox).applyMatrix4(r);let h;if(i)h=k*.5;else{const l=Math.max(s.near,K.distanceToPoint(j.origin));h=gt(s,l,m.resolution)}K.expandByScalar(h),j.intersectsBox(K)!==!1&&(i?be(this,e):we(this,s,e))}onBeforeRender(t){const e=this.material.uniforms;e&&e.resolution&&(t.getViewport(tt),this.material.uniforms.resolution.value.set(tt.z,tt.w))}}const H=new g;function O(a,t,e,i,s,n){const r=2*Math.PI*s/4,u=Math.max(n-2*s,0),m=Math.PI/4;H.copy(t),H[i]=0,H.normalize();const f=.5*r/(r+u),h=1-H.angleTo(a)/m;return Math.sign(H[e])===1?h*f:u/(r+u)+f+f*(1-h)}class ot extends xt{constructor(t=1,e=1,i=1,s=2,n=.1){const r=s*2+1;if(n=Math.min(t/2,e/2,i/2,n),super(1,1,1,r,r,r),this.type="RoundedBoxGeometry",this.parameters={width:t,height:e,depth:i,segments:s,radius:n},r===1)return;const u=this.toNonIndexed();this.index=null,this.attributes.position=u.attributes.position,this.attributes.normal=u.attributes.normal,this.attributes.uv=u.attributes.uv;const m=new g,f=new g,h=new g(t,e,i).divideScalar(2).subScalar(n),l=this.attributes.position.array,b=this.attributes.normal.array,S=this.attributes.uv.array,x=l.length/6,w=new g,A=.5/r;for(let o=0,c=0;o<l.length;o+=3,c+=2)switch(m.fromArray(l,o),f.copy(m),f.x-=Math.sign(f.x)*A,f.y-=Math.sign(f.y)*A,f.z-=Math.sign(f.z)*A,f.normalize(),l[o+0]=h.x*Math.sign(m.x)+f.x*n,l[o+1]=h.y*Math.sign(m.y)+f.y*n,l[o+2]=h.z*Math.sign(m.z)+f.z*n,b[o+0]=f.x,b[o+1]=f.y,b[o+2]=f.z,Math.floor(o/x)){case 0:w.set(1,0,0),S[c+0]=O(w,f,"z","y",n,i),S[c+1]=1-O(w,f,"y","z",n,e);break;case 1:w.set(-1,0,0),S[c+0]=1-O(w,f,"z","y",n,i),S[c+1]=1-O(w,f,"y","z",n,e);break;case 2:w.set(0,1,0),S[c+0]=1-O(w,f,"x","z",n,t),S[c+1]=O(w,f,"z","x",n,i);break;case 3:w.set(0,-1,0),S[c+0]=1-O(w,f,"x","z",n,t),S[c+1]=1-O(w,f,"z","x",n,i);break;case 4:w.set(0,0,1),S[c+0]=1-O(w,f,"x","y",n,t),S[c+1]=1-O(w,f,"y","x",n,e);break;case 5:w.set(0,0,-1),S[c+0]=O(w,f,"x","y",n,t),S[c+1]=1-O(w,f,"y","x",n,e);break}}static fromJSON(t){return new ot(t.width,t.height,t.depth,t.segments,t.radius)}}const xe=new Set(["rover","quadruped","humanoid"]),ve=new g(0,1,0);function Ee(a,{color:t="#426cff",ghost:e=!1}={}){const i=xe.has(a)?a:"rover",s=new Ut;s.name=`robot-${i}${e?"-baseline":""}`,s.userData.visualProfile=i,s.userData.visualOnly=!0;const n={},r=(o,c,d=0,_=.4)=>(n[o]=new vt({color:e?"#93a4b9":c,metalness:e?.12:d,roughness:e?.7:_,transparent:e,opacity:e?.25:1,depthWrite:!e}),n[o]);r("shell","#eceee9",.26,.31),r("edge","#c7cdd0",.62,.3),r("frame","#333d47",.6,.35),r("rubber","#151d24",.02,.88),r("glass","#0c222f",.64,.17),r("accent",t,.42,.26),r("light","#b6e4ff",.1,.23),e||(n.accent.emissive.set(t),n.accent.emissiveIntensity=.16,n.light.emissive.set("#81c9ff"),n.light.emissiveIntensity=.7);const u=new Map,m=(o,c)=>(u.has(o)||u.set(o,c()),u.get(o)),f=(o,c,d,_,p=s)=>{const y=new Y(c,n[d]);return y.name=o,y.position.set(..._),y.castShadow=!e,y.receiveShadow=!e,p.add(y),y},h=(o,c,d,_="shell",p=.015)=>f(o,m(`box:${c}:${p}`,()=>new ot(...c,2,Math.min(p,...c.map(y=>y/3)))),_,d),l=(o,c,d,_,p="frame",y="y",E=20)=>{const z=f(o,m(`cylinder:${c}:${d}:${E}`,()=>new It(c,c,d,E)),p,_);return y==="x"&&(z.rotation.z=-Math.PI/2),y==="z"&&(z.rotation.x=Math.PI/2),z},b=(o,c,d,_,p="frame")=>{const y=new g(...c),E=new g(...d),z=y.distanceTo(E),W=l(o,_,z,y.clone().add(E).multiplyScalar(.5).toArray(),p);return W.quaternion.setFromUnitVectors(ve,E.sub(y).normalize()),W},S=(o,c,d,_,p,y="shell")=>{const E=new g(...c),z=new g(...d),W=h(o,[p,_,E.distanceTo(z)],E.clone().add(z).multiplyScalar(.5).toArray(),y);return W.quaternion.setFromUnitVectors(new g(0,0,1),z.sub(E).normalize()),W},x=(o,c,d,_,p=.026)=>{l(`${o}-rim`,p*1.3,.017,[c,d,_],"edge","x"),l(o,p,.019,[c+.003,d,_],"glass","x"),l(`${o}-optic`,p*.38,.02,[c+.005,d,_],"accent","x",16)},w=(o,c,d=.07)=>{l("lidar-pedestal",d*.42,.065,[o,0,c-.075],"frame","z"),l("lidar-base",d*1.05,.025,[o,0,c-.034],"edge","z"),l("lidar-optical-band",d,.055,[o,0,c],"glass","z",32),l("lidar-signal-ring",d*1.005,.006,[o,0,c+.019],"accent","z",32),l("lidar-cap",d*1.04,.022,[o,0,c+.036],"shell","z",32)};if(i==="rover"){h("underbody",[.66,.35,.12],[0,0,.25],"frame",.025),h("armored-chassis",[.69,.42,.24],[0,0,.405],"shell",.04),h("top-service-panel",[.43,.34,.025],[-.04,0,.532],"edge"),h("deck-inset",[.35,.27,.016],[-.04,0,.546],"frame"),h("sensor-face",[.04,.325,.112],[.356,0,.432],"rubber",.012),x("left-stereo-camera",.385,-.094,.439),x("right-stereo-camera",.385,.094,.439),h("front-status-light",[.016,.064,.011],[.384,0,.444],"light",.003),h("front-skid-plate",[.042,.28,.1],[.36,0,.313],"edge");for(const p of[-1,1]){h("side-armor",[.38,.025,.15],[-.04,p*.218,.408],"shell"),h("side-status-strip",[.24,.01,.014],[-.015,p*.234,.453],"accent",.004);for(const y of[-.18,.18])l("panel-fastener",.008,.028,[y,p*.224,.369],"frame","y",8);b("side-protection-rail",[-.28,p*.253,.293],[.29,p*.253,.293],.012)}for(const p of[-.29,.29]){b("axle",[p,-.3,.171],[p,.3,.171],.023);for(const y of[-1,1]){const E=y*.296;l("all-terrain-tire",.151,.124,[p,E,.163],"rubber","y",32),l("wheel-rim",.086,.009,[p,E+y*.065,.163],"edge"),l("wheel-hub",.061,.012,[p,E+y*.071,.163],"frame"),l("hub-cap",.023,.016,[p,E+y*.079,.163],"accent"),b("suspension-arm",[p*.57,y*.16,.278],[p,E,.163],.024,"frame"),b("suspension-piston",[p*.75,y*.218,.348],[p,y*.253,.178],.012,"edge"),h("wheel-arch",[.23,.145,.027],[p,y*.266,.347],"frame")}}const o=m("treads",()=>new xt(.047,.126,.019)),c=new jt(o,n.rubber,96);c.name="tire-tread-blocks",c.castShadow=!e;const d=new kt;let _=0;for(const p of[-.29,.29])for(const y of[-.296,.296])for(let E=0;E<24;E++){const z=E/24*Math.PI*2;d.position.set(p+Math.sin(z)*.153,y,.163+Math.cos(z)*.153),d.rotation.set(0,z,0),d.updateMatrix(),c.setMatrixAt(_++,d.matrix)}s.add(c);for(const p of[-.4,.41]){b("bumper",[p,-.185,.275],[p,.185,.275],.016);for(const y of[-.185,.185])b("bumper-mount",[p*.8,y,.245],[p,y,.275],.014)}w(-.11,.661,.072),h("roof-camera-mount",[.085,.105,.055],[.17,0,.569],"frame"),x("roof-camera",.218,0,.573,.017),l("antenna-base",.023,.035,[-.26,.142,.555],"rubber","z"),l("antenna",.006,.15,[-.26,.142,.643],"frame","z",10)}else if(i==="quadruped"){h("body-core",[.55,.24,.125],[0,0,.465],"frame",.035),h("dorsal-shell",[.61,.245,.145],[0,0,.501],"shell",.04),h("battery-panel",[.39,.175,.026],[-.025,0,.581],"frame"),h("front-visor",[.038,.207,.072],[.306,0,.511],"glass",.016),x("left-camera",.33,-.062,.51,.018),x("right-camera",.33,.062,.51,.018),h("front-light",[.015,.12,.008],[.328,0,.553],"accent",.002),w(-.125,.65,.047);for(const o of[-1,1]){h("flank-accent",[.24,.011,.019],[0,o*.127,.517],"accent",.004);for(const c of[-1,1]){const d=[c*.223,o*.168,.463],_=[c*.327,o*.216,.262],p=[c*.212,o*.224,.053];l("hip-motor",.055,.089,d,"frame"),l("hip-cover",.039,.01,[d[0],d[1]+o*.048,d[2]],"shell"),l("hip-badge",.021,.012,[d[0],d[1]+o*.054,d[2]],"accent"),S("upper-leg-shell",d,_,.047,.062),l("knee-joint",.035,.066,_,"frame"),l("knee-cap",.024,.012,[_[0],_[1]+o*.039,_[2]],"edge"),b("lower-leg-strut",_,p,.016,"frame");const y=new g(..._).lerp(new g(...p),.1).toArray(),E=new g(..._).lerp(new g(...p),.65).toArray();S("shin-shell",y,E,.036,.039,"edge"),h("foot",[.081,.061,.045],[p[0]+.007,p[1],.0225],"rubber",.017),l("ankle",.024,.052,[p[0],p[1],.052],"frame")}}}else{h("pelvis-frame",[.145,.23,.09],[0,0,.535],"frame",.025),h("pelvis-armor",[.026,.175,.085],[.079,0,.544],"shell"),l("waist-joint",.074,.08,[0,0,.612],"frame","z"),h("torso-shell",[.18,.29,.247],[0,0,.755],"shell",.044),h("upper-back-panel",[.023,.2,.153],[-.096,0,.762],"frame"),h("chest-inset",[.012,.163,.071],[.094,0,.781],"frame"),h("chest-status-light",[.014,.102,.014],[.099,0,.792],"accent",.004),x("depth-sensor",.103,0,.756,.012),l("neck",.039,.076,[0,0,.908],"edge","z"),h("head",[.151,.155,.162],[.005,0,1.001],"shell",.035),h("face-visor",[.026,.137,.079],[.081,0,1.016],"glass",.014),h("eye-light",[.009,.088,.009],[.097,0,1.024],"accent",.003);for(const o of[-1,1]){l("head-hinge",.029,.013,[0,o*.079,.983],"edge");const c=[0,o*.075,.519],d=[.031,o*.084,.301],_=[-.012,o*.086,.102];l("hip-motor",.049,.07,c,"frame"),S("thigh-shell",[0,c[1],.481],[.026,d[1],.331],.083,.105),b("thigh-core",c,d,.029),l("knee-motor",.039,.083,d,"frame"),l("knee-cap",.025,.012,[d[0],d[1]+o*.046,d[2]],"accent"),b("calf-core",d,_,.024,"frame"),S("shin-armor",[.025,d[1],.268],[-.002,_[1],.13],.062,.073),l("ankle-motor",.028,.07,_,"edge"),h("foot-sole",[.174,.088,.032],[.038,o*.086,.016],"rubber",.01),h("foot-armor",[.142,.079,.035],[.025,o*.086,.048],"shell");const p=[0,o*.172,.836],y=[-.008,o*.228,.686],E=[.024,o*.229,.546];l("shoulder-motor",.051,.08,p,"frame"),l("shoulder-cap",.04,.022,[0,o*.221,.836],"shell"),l("shoulder-ring",.024,.026,[0,o*.232,.836],"accent"),b("upper-arm-core",p,y,.019),S("upper-arm-shell",[0,o*.191,.796],[-.005,o*.221,.717],.048,.058),l("elbow-joint",.029,.06,y,"frame"),b("forearm-core",y,E,.018),S("forearm-shell",[0,o*.229,.654],[.019,o*.229,.565],.046,.052),h("hand",[.055,.046,.072],[.026,o*.229,.506],"frame",.012),h("hand-plate",[.01,.04,.05],[.058,o*.229,.513],"shell",.003)}}s.updateMatrixWorld(!0);const A=new $().setFromObject(s);for(const o of s.children)o.position.z-=A.min.z;return s.userData.height=A.max.z-A.min.z,s}class De{constructor(t,e,{visualProfile:i=null,robotModel:s=null,robotModels:n={}}={}){this.host=t;try{this.recordings=Object.entries(e).filter(([,x])=>x),this.scene=new Nt,this.scene.background=new Bt("#1a242e"),this.camera=new Wt(38,1,.01,1e4),this.camera.up.set(0,0,1),this.renderer=new Ht({antialias:!0,alpha:!1}),this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,2)),this.renderer.outputColorSpace=lt,this.renderer.toneMapping=Yt,this.renderer.toneMappingExposure=1.3,this.renderer.shadowMap.enabled=!0,this.renderer.shadowMap.type=Ft,this.renderer.domElement.setAttribute("aria-label","Модель робота и записанные траектории в 3D. Модель условная; движения суставов не записаны. Перетаскивание поворачивает камеру, колесо меняет масштаб."),this.renderer.domElement.setAttribute("role","img"),t.append(this.renderer.domElement),(s||Object.keys(n).length)&&this.renderer.domElement.setAttribute("aria-label","Импортированная модель робота в опорной позе. Движения суставов не записаны. Перетаскивание поворачивает камеру."),this.controls=new ae(this.camera,this.renderer.domElement),this.controls.minDistance=.55,this.controls.maxPolarAngle=Math.PI/2-.015,this.controls.addEventListener("change",()=>this.render());const r=ie(this.recordings.map(([,x])=>x));this.center=new g((r.minX+r.maxX)/2,(r.minY+r.maxY)/2,0),this.span=Math.max(r.maxX-r.minX,r.maxY-r.minY,2),this.robots=[],this.lineMaterials=[],this.scene.fog=new Zt("#1a242e",this.span*2.5,this.span*7);const u=new Gt("#d4e4ff","#34302c",2.3);u.position.set(0,0,1),this.scene.add(u),this.keyLight=new ct("#fff0d8",3.6),this.keyLight.castShadow=!0,this.keyLight.shadow.mapSize.set(2048,2048),this.keyLight.shadow.bias=-15e-5,this.keyLight.shadow.normalBias=.025,this.keyLight.shadow.radius=3,this.scene.add(this.keyLight,this.keyLight.target);for(const[x,w,A]of[["#8badff",2.6,[-4,6,5]],["#ffffff",.7,[4,-6,2]]]){const o=new ct(x,w);o.position.copy(this.center).add(new g(...A)),o.target.position.copy(this.center),this.scene.add(o,o.target)}this.positionLight(this.center,this.span);const m=new Y(new Kt(this.span*16,this.span*16),new vt({color:"#202b35",roughness:.92,metalness:.12}));m.name="coordinate-plane",m.position.copy(this.center),m.position.z=-.003,m.receiveShadow=!0,this.scene.add(m);const f=10**Math.floor(Math.log10(this.span/12)),h=[1,2,5,10].find(x=>x*f>=this.span/12)*f;this.gridStep=h;const l=Math.ceil(this.span*6/h),b=new Xt(l*h,l,"#566673","#374651");b.rotation.x=Math.PI/2,b.position.set(Math.round(this.center.x/h)*h,Math.round(this.center.y/h)*h,-.001),b.material.transparent=!0,b.material.opacity=.48,b.material.depthWrite=!1,this.scene.add(b);for(const[x,w]of this.recordings){const A=se(w).flatMap(d=>d.slice(1).flatMap((_,p)=>[d[p],_].flatMap(({position:y})=>[y.x,y.y,y.z+.012])));if(A.length>=6){const d=new Mt;d.setPositions(A);const _=new Pt({color:Q[x],linewidth:x==="baseline"?2.2:3,dashed:x==="baseline",dashSize:.13,gapSize:.1,transparent:!0,opacity:x==="baseline"?.7:.95,depthWrite:!1}),p=new Se(d,_);p.name=`${x}-recorded-trajectory`,p.computeLineDistances(),this.lineMaterials.push(_),this.scene.add(p)}const o=s??n[x],c=o?Vt(o,x==="baseline"):Ee(i??w.robot.visual_profile??"rover",{color:Q[x],ghost:x==="baseline"});this.scene.add(c),this.robots.push({source:x,replay:w,robot:c})}const S=e.candidate??e.baseline;S&&(this.addMarker(S.recording?S.world.start:S.samples[0].position,S.recording?"ЗАДАННЫЙ СТАРТ":"СТАРТ",Q.candidate,.074),this.addMarker(S.world.goal,"ЦЕЛЬ","#45cfb5",.1)),this.observer=new ResizeObserver(()=>this.resize()),this.observer.observe(t),this.resize(),this.fit(),this.setTime(0)}catch(r){try{this.dispose()}catch{}throw r}}addMarker(t,e,i,s){const n=new Y(new qt(s,s+.025,48),new dt({color:i,side:$t,depthWrite:!1}));n.position.set(t.x,t.y,t.z+.023),this.scene.add(n);const r=new Y(new Qt(s*.4,32),new dt({color:i,transparent:!0,opacity:.75,depthWrite:!1}));r.position.copy(n.position),this.scene.add(r);const u=document.createElement("canvas");u.width=256,u.height=80;const m=u.getContext("2d");if(!m)return;m.fillStyle="rgba(18, 27, 36, 0.8)",m.beginPath(),m.roundRect(10,10,236,60,15),m.fill(),m.font="600 29px system-ui, sans-serif",m.textAlign="center",m.textBaseline="middle",m.fillStyle="#e8eef4",m.fillText(e,128,42);const f=new Jt(u);f.colorSpace=lt;const h=new te(new ee({map:f,transparent:!0,depthWrite:!1})),l=Math.max(.43,this.span*.07);h.scale.set(l,l*80/256,1),h.position.set(t.x,t.y,t.z+.28),this.scene.add(h)}resize(){const t=Math.max(1,this.host.clientWidth),e=Math.max(1,this.host.clientHeight);this.renderer.setSize(t,e),this.camera.aspect=t/e,this.camera.updateProjectionMatrix();for(const i of this.lineMaterials)i.resolution.set(t,e);this.render()}positionLight(t,e){this.keyLight.position.copy(t).add(new g(3,-4,7).multiplyScalar(Math.max(1,e/6))),this.keyLight.target.position.copy(t);const i=this.keyLight.shadow.camera,s=Math.max(1.5,e*.8);i.left=i.bottom=-s,i.right=i.top=s,i.near=.1,i.far=Math.max(25,e*6),i.updateProjectionMatrix()}render(){this.renderer.render(this.scene,this.camera)}fit(){this.focused=!1;const t=Math.max(1,1/this.camera.aspect);this.camera.position.copy(this.center).add(new g(this.span*.7,-this.span*.9,this.span*.85).multiplyScalar(t)),this.camera.far=Math.max(1e3,this.span*100),this.camera.updateProjectionMatrix(),this.controls.target.copy(this.center),this.controls.maxDistance=this.span*12,this.positionLight(this.center,this.span),this.controls.update(),this.render()}focusRobot(){const t=this.robots.find(({source:r})=>r==="candidate")??this.robots[0];if(!t||!t.robot.visible)return;const{robot:e}=t,i=e.position.clone().add(new g(0,0,e.userData.height*.43)),s=Math.max(e.userData.height,.8)*Math.max(1,1/this.camera.aspect),n=new g(1.55,-2.1,1.1).multiplyScalar(s);n.applyAxisAngle(new g(0,0,1),e.rotation.z),this.camera.position.copy(i).add(n),this.controls.target.copy(i),this.positionLight(i,2.5),this.focused=!0,this.focusedRobot=e,this.controls.update(),this.render()}setTime(t){const e=this.focused?this.focusedRobot.position.clone():null;for(const{replay:i,robot:s}of this.robots){const{pose:n}=ne(i,t);s.visible=!!n,n&&(s.position.set(n.position.x,n.position.y,n.position.z),s.rotation.z=n.orientation.yaw)}if(e){const i=this.focusedRobot.position.clone().sub(e);this.camera.position.add(i),this.controls.target.add(i),this.positionLight(this.controls.target,2.5),this.controls.update()}this.render()}dispose(){this.observer?.disconnect(),this.controls?.dispose();const t=new Set,e=new Set,i=new Set;this.scene?.traverse(s=>{s.geometry&&t.add(s.geometry);for(const n of Array.isArray(s.material)?s.material:[s.material])if(n){e.add(n);for(const r of Object.values(n))r?.isTexture&&i.add(r)}s.isInstancedMesh&&s.dispose(),s.isLight&&s.shadow&&s.shadow.dispose()}),i.forEach(s=>s.dispose()),t.forEach(s=>s.dispose()),e.forEach(s=>s.dispose()),this.renderer?.dispose(),this.renderer?.forceContextLoss(),this.renderer?.domElement.remove()}}export{De as SceneView};
