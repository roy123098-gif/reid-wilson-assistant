# Android app path

The website is now an installable Progressive Web App (PWA). After it is deployed on HTTPS, an Android user can open the full app URL in Chrome and choose **Install app**.

For a Google Play Store release, use a Trusted Web Activity (TWA):

1. Host the app on a dedicated HTTPS address such as `app.reidandwilson.com`. Link to that address from Wix instead of placing the entire app inside an iframe.
2. Confirm the PWA manifest, icons, service worker, privacy policy, terms, and offline screen load from that same address.
3. Create the Android wrapper with Android Studio or Bubblewrap using package name `com.reidandwilson.taxpayeradvisory`.
4. Publish `/.well-known/assetlinks.json` with the Play signing certificate fingerprint so Android can verify the website and app belong together.
5. Test login-free use, encrypted goal storage, offline behavior, screen-reader labels, small phones, and deletion/reset behavior.
6. Complete the Play Console data-safety, content-rating, privacy, financial-features, and testing declarations. Check the current Google Play policy and target API requirement immediately before submission.

The web service must remain online because tax, EIC, budget, and goal calculations use its API. The service worker intentionally never caches API responses or taxpayer data.
