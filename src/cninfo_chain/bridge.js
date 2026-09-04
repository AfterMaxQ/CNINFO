(() => {
  if (window.__cninfoBridge) return;

  const allowedPaths = new Set([
    "/ics/aasKnowledgeBase/chaincenter/chainlist/list",
    "/ics/aasKnowledgeBase/chaincenter/chainlist/dynamicChainMapNew",
    "/ics/aasKnowledgeBase/industry/industry-info",
    "/ics/aasKnowledgeBase/industryDetail/companyIncome",
    "/ics/aasKnowledgeBase/chaincenter/searchOtherListed",
    "/ics/aasKnowledgeBase/chaincenter/searchglobalNew",
  ]);
  const templates = new Map();
  const originalFetch = window.fetch.bind(window);
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  const originalSend = XMLHttpRequest.prototype.send;

  function asUrl(value) {
    try {
      return new URL(value, window.location.href);
    } catch (_) {
      return null;
    }
  }

  function remember(urlValue, headersValue) {
    const url = asUrl(urlValue);
    if (!url || url.origin !== window.location.origin || !allowedPaths.has(url.pathname)) return;
    const headers = new Headers(headersValue || {});
    templates.set(url.pathname, { headers });
  }

  window.fetch = function wrappedFetch(input, init = {}) {
    const request = input instanceof Request ? input : null;
    const url = request ? request.url : input;
    const headers = new Headers(request ? request.headers : {});
    new Headers(init.headers || {}).forEach((value, key) => headers.set(key, value));
    remember(url, headers);
    return originalFetch(input, init);
  };

  XMLHttpRequest.prototype.open = function wrappedOpen(method, url, ...rest) {
    this.__cninfoObservedUrl = url;
    this.__cninfoObservedHeaders = new Headers();
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.setRequestHeader = function wrappedSetRequestHeader(name, value) {
    if (this.__cninfoObservedHeaders) this.__cninfoObservedHeaders.set(name, value);
    return originalSetRequestHeader.call(this, name, value);
  };

  XMLHttpRequest.prototype.send = function wrappedSend(body) {
    remember(this.__cninfoObservedUrl, this.__cninfoObservedHeaders);
    return originalSend.call(this, body);
  };

  window.__cninfoBridge = Object.freeze({
    ready() {
      return templates.size > 0;
    },
    async call(request) {
      if (!request || !allowedPaths.has(request.path)) {
        throw new Error("endpoint is not allowed");
      }
      const template = templates.get(request.path) || templates.values().next().value;
      if (!template) throw new Error("no authenticated request template captured");

      const headers = new Headers(template.headers);
      let body;
      if (request.encoding === "json") {
        headers.set("content-type", "application/json;charset=UTF-8");
        body = JSON.stringify(request.params);
      } else if (request.encoding === "form") {
        headers.set("content-type", "application/x-www-form-urlencoded;charset=UTF-8");
        body = new URLSearchParams(request.params).toString();
      } else {
        throw new Error("unsupported request encoding");
      }
      const response = await originalFetch(request.path, {
        method: "POST",
        headers,
        body,
        credentials: "include",
      });
      const payload = await response.json();
      return { status: response.status, json: payload };
    },
  });
})();
