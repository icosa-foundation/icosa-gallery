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
}
