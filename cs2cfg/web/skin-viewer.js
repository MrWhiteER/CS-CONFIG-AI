// A small, self-contained glTF-binary (.glb) viewer: orbit, zoom, nothing else.
//
// No library is vendored for this -- every other script in this app is
// written in-house rather than pulled from a CDN, and a weapon export is
// simple enough (one mesh, sometimes a handful of parts, one base colour
// texture) that a full glTF implementation would be solving problems this
// never has. It reads exactly what cs2cfg.skin_render's exports contain:
// POSITION/NORMAL/TEXCOORD_0, triangle primitives, a node hierarchy with
// TRS or matrix transforms, and at most one base-colour texture per
// material. Anything stranger in the file is skipped rather than guessed at.
(function (global) {
  "use strict";

  const GLB_MAGIC = 0x46546c67;
  const CHUNK_JSON = 0x4e4f534a;
  const CHUNK_BIN = 0x004e4942;

  function parseGLB(buffer) {
    const dv = new DataView(buffer);
    if (dv.getUint32(0, true) !== GLB_MAGIC) {
      throw new Error("not a .glb file");
    }
    const length = dv.getUint32(8, true);
    let offset = 12;
    let json = null;
    let bin = null;
    while (offset < length) {
      const chunkLength = dv.getUint32(offset, true);
      const chunkType = dv.getUint32(offset + 4, true);
      const chunkStart = offset + 8;
      if (chunkType === CHUNK_JSON) {
        const text = new TextDecoder("utf-8").decode(
          new Uint8Array(buffer, chunkStart, chunkLength));
        json = JSON.parse(text);
      } else if (chunkType === CHUNK_BIN) {
        bin = buffer.slice(chunkStart, chunkStart + chunkLength);
      }
      offset = chunkStart + chunkLength;
    }
    if (!json) throw new Error("the model has no scene data");
    return { json, bin };
  }

  const COMPONENT_SIZES = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
  const TYPE_COUNTS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

  // Everything needed to point a vertexAttribPointer (or drawElements) at
  // an accessor, given that its bufferView is uploaded as its own GL buffer
  // starting at byte 0 -- so only the accessor's own byteOffset matters
  // here, never the bufferView's (that part of the offset was already
  // consumed when the view's bytes were sliced out for upload).
  function accessorInfo(json, index) {
    const accessor = json.accessors[index];
    const bufferView = json.bufferViews[accessor.bufferView];
    return {
      accessor, bufferView,
      componentSize: COMPONENT_SIZES[accessor.componentType],
      numComponents: TYPE_COUNTS[accessor.type],
      byteOffset: accessor.byteOffset || 0,
      stride: bufferView.byteStride || 0,
    };
  }

  // Reads a VEC3 FLOAT accessor straight out of the raw binary chunk, for
  // bounding-box math -- independent of anything uploaded to the GPU,
  // since WebGL buffers cannot cheaply be read back.
  function readVec3Array(json, bin, accessorIndex) {
    const info = accessorInfo(json, accessorIndex);
    const view = info.bufferView;
    const base = (view.byteOffset || 0) + info.byteOffset;
    const stride = info.stride || info.numComponents * info.componentSize;
    const count = info.accessor.count;
    const dv = new DataView(bin);
    const out = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const at = base + i * stride;
      out[i * 3] = dv.getFloat32(at, true);
      out[i * 3 + 1] = dv.getFloat32(at + 4, true);
      out[i * 3 + 2] = dv.getFloat32(at + 8, true);
    }
    return out;
  }

  // -- tiny mat4/vec3 helpers -- just what this needs, nothing generic ----
  const mat4 = {
    identity: () => [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
    multiply: (a, b) => {
      const out = new Array(16);
      for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
        let sum = 0;
        for (let k = 0; k < 4; k++) sum += a[k * 4 + r] * b[c * 4 + k];
        out[c * 4 + r] = sum;
      }
      return out;
    },
    fromTRS: (t, r, s) => {
      const [x, y, z, w] = r;
      const x2 = x + x, y2 = y + y, z2 = z + z;
      const xx = x * x2, xy = x * y2, xz = x * z2;
      const yy = y * y2, yz = y * z2, zz = z * z2;
      const wx = w * x2, wy = w * y2, wz = w * z2;
      return [
        (1 - (yy + zz)) * s[0], (xy + wz) * s[0], (xz - wy) * s[0], 0,
        (xy - wz) * s[1], (1 - (xx + zz)) * s[1], (yz + wx) * s[1], 0,
        (xz + wy) * s[2], (yz - wx) * s[2], (1 - (xx + yy)) * s[2], 0,
        t[0], t[1], t[2], 1,
      ];
    },
    perspective: (fovy, aspect, near, far) => {
      const f = 1 / Math.tan(fovy / 2);
      return [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (far + near) / (near - far), -1,
        0, 0, (2 * far * near) / (near - far), 0,
      ];
    },
    lookAt: (eye, center, up) => {
      const sub = (a, b) => [a[0]-b[0], a[1]-b[1], a[2]-b[2]];
      const norm = (v) => { const l = Math.hypot(v[0],v[1],v[2]) || 1; return [v[0]/l,v[1]/l,v[2]/l]; };
      const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
      const zAxis = norm(sub(eye, center));
      const xAxis = norm(cross(up, zAxis));
      const yAxis = cross(zAxis, xAxis);
      return [
        xAxis[0], yAxis[0], zAxis[0], 0,
        xAxis[1], yAxis[1], zAxis[1], 0,
        xAxis[2], yAxis[2], zAxis[2], 0,
        -(xAxis[0]*eye[0]+xAxis[1]*eye[1]+xAxis[2]*eye[2]),
        -(yAxis[0]*eye[0]+yAxis[1]*eye[1]+yAxis[2]*eye[2]),
        -(zAxis[0]*eye[0]+zAxis[1]*eye[1]+zAxis[2]*eye[2]), 1,
      ];
    },
    // Upper-left 3x3, transposed-inverse would be the correct normal matrix
    // under non-uniform scale; a weapon export is uniform enough that the
    // plain upper-left block is a fair approximation and skips a 3x3 invert.
    normalFrom: (m) => [m[0],m[1],m[2], m[4],m[5],m[6], m[8],m[9],m[10]],
    apply: (m, p) => [
      m[0]*p[0] + m[4]*p[1] + m[8]*p[2] + m[12],
      m[1]*p[0] + m[5]*p[1] + m[9]*p[2] + m[13],
      m[2]*p[0] + m[6]*p[1] + m[10]*p[2] + m[14],
    ],
  };

  const VERTEX_SRC = `
    attribute vec3 aPosition;
    attribute vec3 aNormal;
    attribute vec2 aUV;
    uniform mat4 uModel;
    uniform mat4 uView;
    uniform mat4 uProjection;
    uniform mat3 uNormalMatrix;
    varying vec3 vNormal;
    varying vec2 vUV;
    void main() {
      vNormal = uNormalMatrix * aNormal;
      vUV = aUV;
      gl_Position = uProjection * uView * uModel * vec4(aPosition, 1.0);
    }
  `;

  const FRAGMENT_SRC = `
    precision mediump float;
    varying vec3 vNormal;
    varying vec2 vUV;
    uniform sampler2D uTexture;
    uniform bool uHasTexture;
    uniform vec4 uBaseColor;
    uniform vec3 uLightDir;
    void main() {
      vec4 base = uHasTexture ? texture2D(uTexture, vUV) : uBaseColor;
      vec3 n = normalize(vNormal);
      // Key light plus a weaker fill from roughly the opposite side -- a
      // single directional light left anything not facing it at a flat,
      // hard-to-read 35% brightness, which on a dark backdrop made most of
      // a model disappear into its own shadow.
      float key = max(dot(n, -uLightDir), 0.0);
      float fill = max(dot(n, uLightDir), 0.0);
      float light = 0.6 + 0.32 * key + 0.2 * fill;
      gl_FragColor = vec4(base.rgb * light, base.a);
    }
  `;

  // The ground disc: unit circle in local space, scaled/placed per draw.
  // Alpha fades from the centre (vRadius 0) to the rim (vRadius 1) entirely
  // in the fragment shader, so the single ring of vertices needs no extra
  // per-vertex data of its own.
  const GROUND_VERTEX_SRC = `
    attribute vec3 aPosition;
    uniform mat4 uModel;
    uniform mat4 uView;
    uniform mat4 uProjection;
    varying float vRadius;
    void main() {
      vRadius = length(aPosition.xz);
      gl_Position = uProjection * uView * uModel * vec4(aPosition, 1.0);
    }
  `;
  const GROUND_FRAGMENT_SRC = `
    precision mediump float;
    varying float vRadius;
    void main() {
      float a = (1.0 - smoothstep(0.0, 1.0, vRadius)) * 0.35;
      gl_FragColor = vec4(0.0, 0.0, 0.0, a);
    }
  `;

  function compile(gl, type, src) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error("shader failed: " + info);
    }
    return shader;
  }

  class SkinViewer {
    constructor(canvas) {
      this.canvas = canvas;
      const gl = canvas.getContext("webgl", { antialias: true, alpha: true });
      if (!gl) throw new Error("WebGL is not available");
      this.gl = gl;
      // A multi-part weapon export easily has more than 65535 vertices, so
      // its indices come out as 32-bit -- WebGL1 can only draw those with
      // this extension enabled.
      this.hasUintIndices = !!gl.getExtension("OES_element_index_uint");

      const program = gl.createProgram();
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SRC));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SRC));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error("program link failed: " + gl.getProgramInfoLog(program));
      }
      this.program = program;
      this.attribs = {
        position: gl.getAttribLocation(program, "aPosition"),
        normal: gl.getAttribLocation(program, "aNormal"),
        uv: gl.getAttribLocation(program, "aUV"),
      };
      this.uniforms = {
        model: gl.getUniformLocation(program, "uModel"),
        view: gl.getUniformLocation(program, "uView"),
        projection: gl.getUniformLocation(program, "uProjection"),
        normalMatrix: gl.getUniformLocation(program, "uNormalMatrix"),
        texture: gl.getUniformLocation(program, "uTexture"),
        hasTexture: gl.getUniformLocation(program, "uHasTexture"),
        baseColor: gl.getUniformLocation(program, "uBaseColor"),
        lightDir: gl.getUniformLocation(program, "uLightDir"),
      };

      this.yaw = 0.6;
      this.pitch = 0.3;
      this.distance = 1.0;
      this.center = [0, 0, 0];
      this.radius = 1.0;
      this.groundY = 0;
      this.primitives = [];
      this.glBuffers = [];
      this.glTextures = [];
      this.overrideTexture = null;

      this._setupGround();
      this._bindControls();
    }

    // A simple flat disc under the model -- a real character and map is
    // out of reach for this (see the module comment); this is the honest,
    // scoped version: give the preview a surface to sit on and a soft
    // shadow-like falloff, which reads as "presented" instead of "floating
    // in a void" without claiming to be anything more than that. A tiny
    // dedicated shader rather than extending the main one, since alpha
    // falloff and blending are the only things it needs and nothing about
    // a weapon's own material applies to it.
    _setupGround() {
      const gl = this.gl;
      const program = gl.createProgram();
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, GROUND_VERTEX_SRC));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, GROUND_FRAGMENT_SRC));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error("ground shader link failed: " + gl.getProgramInfoLog(program));
      }
      this.groundProgram = program;
      this.groundAttribs = { position: gl.getAttribLocation(program, "aPosition") };
      this.groundUniforms = {
        model: gl.getUniformLocation(program, "uModel"),
        view: gl.getUniformLocation(program, "uView"),
        projection: gl.getUniformLocation(program, "uProjection"),
      };

      const rings = 32;
      const positions = [0, 0, 0];
      for (let i = 0; i <= rings; i++) {
        const a = (i / rings) * Math.PI * 2;
        positions.push(Math.cos(a), 0, Math.sin(a));
      }
      const indices = [];
      for (let i = 1; i <= rings; i++) indices.push(0, i, i + 1);

      this.groundCount = indices.length;
      this.groundPosBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, this.groundPosBuf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(positions), gl.STATIC_DRAW);
      this.groundIdxBuf = gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.groundIdxBuf);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
    }

    _bindControls() {
      const canvas = this.canvas;
      let dragging = false, lastX = 0, lastY = 0;
      canvas.addEventListener("pointerdown", (e) => {
        dragging = true; lastX = e.clientX; lastY = e.clientY;
        canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener("pointerup", () => { dragging = false; });
      canvas.addEventListener("pointermove", (e) => {
        if (!dragging) return;
        this.yaw += (e.clientX - lastX) * 0.01;
        this.pitch = Math.max(-1.4, Math.min(1.4, this.pitch + (e.clientY - lastY) * 0.01));
        lastX = e.clientX; lastY = e.clientY;
        this._draw();
      });
      canvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        this.distance = Math.max(this.radius * 0.5, Math.min(this.radius * 8, this.distance * (1 + e.deltaY * 0.001)));
        this._draw();
      }, { passive: false });
    }

    dispose() {
      const gl = this.gl;
      this.glBuffers.forEach((b) => gl.deleteBuffer(b));
      this.glTextures.forEach((t) => gl.deleteTexture(t));
      this.glBuffers = [];
      this.glTextures = [];
      this.primitives = [];
      if (this.overrideTexture) {
        gl.deleteTexture(this.overrideTexture);
        this.overrideTexture = null;
      }
    }

    // The weapon model's own material is the bare factory default -- a
    // skin's actual paint lives in a separate file CS2 composites on at
    // runtime (see cs2cfg.skin_render.texture_path) and is fetched
    // separately. This overrides every primitive's texture at once, since
    // a reskinned weapon is painted as one surface, not per sub-mesh.
    //
    // `tiled` has to come from the server (cs2cfg.skin_render.TextureInfo,
    // via the X-Texture-Tiled response header): most skins are one image
    // mapped once over the whole gun and need clamping, but a handful (the
    // "Gunsmith" patina finishes, like Case Hardened) are a small pattern
    // meant to repeat across it. Repeating the wrong kind tiles a large
    // detailed image across many small UV triangles, which looks like the
    // model shattered rather than like a texture that merely clamped badly.
    async setOverrideTexture(arrayBuffer, mimeType, tiled) {
      const gl = this.gl;
      const blob = new Blob([arrayBuffer], { type: mimeType || "image/png" });
      const bitmap = await createImageBitmap(blob);
      if (this.overrideTexture) gl.deleteTexture(this.overrideTexture);
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
      gl.generateMipmap(gl.TEXTURE_2D);
      const wrap = tiled ? gl.REPEAT : gl.CLAMP_TO_EDGE;
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      this.overrideTexture = tex;
      this._draw();
    }

    async load(arrayBuffer) {
      this.dispose();
      const { json, bin } = parseGLB(arrayBuffer);
      const gl = this.gl;

      // One GL buffer per raw bufferView actually referenced, uploaded once
      // even when more than one accessor (e.g. an interleaved POSITION and
      // NORMAL) shares it.
      const viewBuffers = new Map();
      const uploadView = (viewIndex, target) => {
        if (viewBuffers.has(viewIndex)) return viewBuffers.get(viewIndex);
        const view = json.bufferViews[viewIndex];
        const bytes = new Uint8Array(bin, view.byteOffset || 0, view.byteLength);
        const buf = gl.createBuffer();
        gl.bindBuffer(target, buf);
        gl.bufferData(target, bytes, gl.STATIC_DRAW);
        viewBuffers.set(viewIndex, buf);
        this.glBuffers.push(buf);
        return buf;
      };

      // Textures: at most one base-colour image per material, decoded with
      // the browser's own image codecs -- nothing here parses image bytes.
      const textures = [];
      if (json.images && json.textures) {
        for (const tex of json.textures) {
          const image = json.images[tex.source];
          if (image == null || image.bufferView == null) { textures.push(null); continue; }
          const view = json.bufferViews[image.bufferView];
          const bytes = new Uint8Array(bin, view.byteOffset || 0, view.byteLength);
          const blob = new Blob([bytes], { type: image.mimeType || "image/png" });
          try {
            const bitmap = await createImageBitmap(blob);
            const glTex = gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D, glTex);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bitmap);
            gl.generateMipmap(gl.TEXTURE_2D);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
            this.glTextures.push(glTex);
            textures.push(glTex);
          } catch (err) {
            textures.push(null);
          }
        }
      }

      const materialFor = (materialIndex) => {
        const mat = (json.materials || [])[materialIndex] || {};
        const pbr = mat.pbrMetallicRoughness || {};
        const baseColor = pbr.baseColorFactor || [0.75, 0.75, 0.78, 1];
        let texture = null;
        if (pbr.baseColorTexture && textures[pbr.baseColorTexture.index]) {
          texture = textures[pbr.baseColorTexture.index];
        }
        return { baseColor, texture };
      };

      // Walk the node hierarchy, collecting every mesh primitive with its
      // accumulated world transform -- a weapon export is often several
      // parts (body, mag, slide) as separate nodes, not one single mesh.
      const primitives = [];
      const localMatrix = (node) => node.matrix || mat4.fromTRS(
        node.translation || [0, 0, 0], node.rotation || [0, 0, 0, 1], node.scale || [1, 1, 1]);

      const visit = (nodeIndex, parentMatrix) => {
        const node = json.nodes[nodeIndex];
        const world = mat4.multiply(parentMatrix, localMatrix(node));
        if (node.mesh != null) {
          for (const prim of json.meshes[node.mesh].primitives) {
            if (prim.mode != null && prim.mode !== 4) continue;  // triangles only
            if (prim.attributes.POSITION == null) continue;

            const posInfo = accessorInfo(json, prim.attributes.POSITION);
            const normInfo = prim.attributes.NORMAL != null ? accessorInfo(json, prim.attributes.NORMAL) : null;
            const uvInfo = prim.attributes.TEXCOORD_0 != null ? accessorInfo(json, prim.attributes.TEXCOORD_0) : null;
            const indexInfo = prim.indices != null ? accessorInfo(json, prim.indices) : null;

            primitives.push({
              world,
              posArray: readVec3Array(json, bin, prim.attributes.POSITION),
              posBuf: uploadView(json.accessors[prim.attributes.POSITION].bufferView, gl.ARRAY_BUFFER),
              posInfo,
              normBuf: normInfo ? uploadView(json.accessors[prim.attributes.NORMAL].bufferView, gl.ARRAY_BUFFER) : null,
              normInfo,
              uvBuf: uvInfo ? uploadView(json.accessors[prim.attributes.TEXCOORD_0].bufferView, gl.ARRAY_BUFFER) : null,
              uvInfo,
              indexBuf: indexInfo ? uploadView(json.accessors[prim.indices].bufferView, gl.ELEMENT_ARRAY_BUFFER) : null,
              indexInfo,
              count: indexInfo ? indexInfo.accessor.count : posInfo.accessor.count,
              material: materialFor(prim.material),
            });
          }
        }
        for (const child of node.children || []) visit(child, world);
      };
      const scene = json.scenes[json.scene || 0];
      for (const rootIndex of scene.nodes || []) visit(rootIndex, mat4.identity());
      this.primitives = primitives;

      this._frame();
      this._draw();
    }

    // Auto-frame: the exported model's own units/position are unknown, so
    // the camera is aimed at the vertex bounding box rather than assuming
    // anything about scale.
    _frame() {
      let min = [Infinity, Infinity, Infinity];
      let max = [-Infinity, -Infinity, -Infinity];
      for (const prim of this.primitives) {
        const arr = prim.posArray;
        for (let i = 0; i < arr.length; i += 3) {
          const p = mat4.apply(prim.world, [arr[i], arr[i + 1], arr[i + 2]]);
          for (let k = 0; k < 3; k++) {
            if (p[k] < min[k]) min[k] = p[k];
            if (p[k] > max[k]) max[k] = p[k];
          }
        }
      }
      if (!isFinite(min[0])) { min = [-1, -1, -1]; max = [1, 1, 1]; }
      this.center = [(min[0]+max[0])/2, (min[1]+max[1])/2, (min[2]+max[2])/2];
      this.radius = Math.max(Math.hypot(max[0]-min[0], max[1]-min[1], max[2]-min[2]) / 2, 0.001);
      this.distance = this.radius * 2.5;
      this.groundY = min[1];
    }

    resize() {
      const canvas = this.canvas;
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (w > 0 && h > 0 && (canvas.width !== w || canvas.height !== h)) {
        canvas.width = w; canvas.height = h;
      }
      this._draw();
    }

    _draw() {
      const gl = this.gl;
      const w = this.canvas.width || 1, h = this.canvas.height || 1;
      gl.viewport(0, 0, w, h);
      gl.enable(gl.DEPTH_TEST);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      if (!this.primitives.length) return;

      const eye = [
        this.center[0] + this.distance * Math.cos(this.pitch) * Math.sin(this.yaw),
        this.center[1] + this.distance * Math.sin(this.pitch),
        this.center[2] + this.distance * Math.cos(this.pitch) * Math.cos(this.yaw),
      ];
      const view = mat4.lookAt(eye, this.center, [0, 1, 0]);
      const projection = mat4.perspective(Math.PI / 4, w / h, this.radius * 0.02, this.radius * 50);

      this._drawGround(view, projection);

      gl.useProgram(this.program);
      gl.uniformMatrix4fv(this.uniforms.view, false, view);
      gl.uniformMatrix4fv(this.uniforms.projection, false, projection);
      gl.uniform3f(this.uniforms.lightDir, 0.4, -0.7, -0.6);

      for (const prim of this.primitives) {
        gl.uniformMatrix4fv(this.uniforms.model, false, prim.world);
        gl.uniformMatrix3fv(this.uniforms.normalMatrix, false, mat4.normalFrom(prim.world));

        this._bindAttr(this.attribs.position, prim.posBuf, prim.posInfo, 3);
        if (prim.normBuf) this._bindAttr(this.attribs.normal, prim.normBuf, prim.normInfo, 3);
        else gl.disableVertexAttribArray(this.attribs.normal);
        if (prim.uvBuf) this._bindAttr(this.attribs.uv, prim.uvBuf, prim.uvInfo, 2);
        else gl.disableVertexAttribArray(this.attribs.uv);

        const activeTexture = this.overrideTexture || prim.material.texture;
        if (activeTexture) {
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, activeTexture);
          gl.uniform1i(this.uniforms.texture, 0);
          gl.uniform1i(this.uniforms.hasTexture, 1);
        } else {
          gl.uniform1i(this.uniforms.hasTexture, 0);
          gl.uniform4fv(this.uniforms.baseColor, prim.material.baseColor);
        }

        if (prim.indexBuf) {
          gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, prim.indexBuf);
          const componentType = prim.indexInfo.accessor.componentType;
          const type = componentType === 5121 ? gl.UNSIGNED_BYTE
            : componentType === 5125 ? gl.UNSIGNED_INT
            : gl.UNSIGNED_SHORT;
          if (componentType === 5125 && !this.hasUintIndices) continue;
          gl.drawElements(gl.TRIANGLES, prim.count, type, prim.indexInfo.byteOffset);
        } else {
          gl.drawArrays(gl.TRIANGLES, 0, prim.count);
        }
      }
    }

    _drawGround(view, projection) {
      const gl = this.gl;
      const scale = this.radius * 2.2;
      const model = mat4.fromTRS(
        [this.center[0], this.groundY, this.center[2]], [0, 0, 0, 1], [scale, 1, scale]);

      gl.useProgram(this.groundProgram);
      gl.uniformMatrix4fv(this.groundUniforms.model, false, model);
      gl.uniformMatrix4fv(this.groundUniforms.view, false, view);
      gl.uniformMatrix4fv(this.groundUniforms.projection, false, projection);

      gl.bindBuffer(gl.ARRAY_BUFFER, this.groundPosBuf);
      gl.enableVertexAttribArray(this.groundAttribs.position);
      gl.vertexAttribPointer(this.groundAttribs.position, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.groundIdxBuf);

      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.depthMask(false);
      gl.drawElements(gl.TRIANGLES, this.groundCount, gl.UNSIGNED_SHORT, 0);
      gl.depthMask(true);
      gl.disable(gl.BLEND);
    }

    _bindAttr(location, buffer, info, size) {
      const gl = this.gl;
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.enableVertexAttribArray(location);
      const stride = info.stride || size * info.componentSize;
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, stride, info.byteOffset);
    }
  }

  global.SkinViewer = SkinViewer;
})(window);
