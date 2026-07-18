"use client";

import Script from "next/script";
import { config } from "@/lib/config";
import { useConsent } from "@/components/cookie-consent";

/* Analytics placeholders — each script renders ONLY when its env id is set
   (config, see .env.example) AND the visitor has accepted cookies. Declining
   (or not answering) injects nothing. Rendered from layout only when
   hasAnalytics is true. No noscript pixel fallbacks: they cannot be
   consent-gated. */

export function Analytics() {
  const consent = useConsent();
  if (consent !== "accepted") return null;

  return (
    <>
      {config.ga4Id && (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${config.ga4Id}`}
            strategy="afterInteractive"
          />
          <Script id="ga4-init" strategy="afterInteractive">
            {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${config.ga4Id}');`}
          </Script>
        </>
      )}
      {config.metaPixelId && (
        <Script id="meta-pixel" strategy="afterInteractive">
          {`!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','${config.metaPixelId}');fbq('track','PageView');`}
        </Script>
      )}
      {config.linkedInTagId && (
        <Script id="linkedin-insight" strategy="afterInteractive">
          {`window._linkedin_partner_id='${config.linkedInTagId}';window._linkedin_data_partner_ids=window._linkedin_data_partner_ids||[];window._linkedin_data_partner_ids.push(window._linkedin_partner_id);(function(l){if(!l){window.lintrk=function(a,b){window.lintrk.q.push([a,b])};window.lintrk.q=[]}var s=document.getElementsByTagName('script')[0];var b=document.createElement('script');b.type='text/javascript';b.async=true;b.src='https://snap.licdn.com/li.lms-analytics/insight.min.js';s.parentNode.insertBefore(b,s)})(window.lintrk);`}
        </Script>
      )}
    </>
  );
}
