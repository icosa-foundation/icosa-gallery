vcl 4.0;
import proxy;

backend default {
    .host = "django";
    .port = "8000";
}

sub vcl_recv {
    if(!req.http.X-Forwarded-Proto) {
        if (proxy.is_ssl()) {
            set req.http.X-Forwarded-Proto = "https";
        } else {
            set req.http.X-Forwarded-Proto = "http";
        }
    }    
}

sub vcl_backend_response {
    if(beresp.http.Vary) {
        set beresp.http.Vary = beresp.http.Vary + ", X-Forwarded-Proto";
    } else {
        set beresp.http.Vary = "X-Forwarded-Proto";
    }

    set beresp.http.X-Url = bereq.url;

    // Allow esi includes for pages.
    set beresp.do_esi = true;

    // Default non-contentious ttl, just to take the edge off.
    set beresp.ttl = 2s;

    // Long cache for individual assets or oembeds.
    if (bereq.url ~ "^\/v1\/(assets|oembed)/.+$") {
        set beresp.ttl = 60s;
    }

    // All /v1/* routes, except for /v1/docs that include the querystring
    // curated=true where `true` can also be `True`.
    // Cache really agressively.
    if (bereq.url ~ "^\/v1\/(?!docs).*\?.*curated=[tT]rue.*$") {
        set beresp.ttl = 172800s; // 2 days
    }
}

