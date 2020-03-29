package com.example.myday;

import android.content.BroadcastReceiver;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import com.android.volley.RequestQueue;
import com.android.volley.toolbox.Volley;
import com.firebase.ui.auth.AuthUI;
import com.google.android.gms.tasks.OnCompleteListener;
import com.google.android.gms.tasks.Task;
import com.google.firebase.auth.AuthResult;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.database.DataSnapshot;
import com.google.firebase.database.DatabaseError;
import com.google.firebase.database.DatabaseReference;
import com.google.firebase.database.FirebaseDatabase;
import com.google.firebase.database.ValueEventListener;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Calendar;
import java.util.Date;

import butterknife.ButterKnife;
import butterknife.OnClick;

public class HomeActivity extends AppCompatActivity {
    @OnClick(R.id.btn_exit) void submit() {
        finish();
        System.exit(0);
    }

    RequestQueue requestQueue;
    FirebaseAuth mAuth;
    FirebaseDatabase database;
    DatabaseReference morningRef;
    Date morning;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_home);
        ButterKnife.bind(this);

        // Initialize Firebase database.
        this.mAuth = FirebaseAuth.getInstance();
        // Check if user is signed in (non-null) and update UI accordingly.
        FirebaseUser currentUser = mAuth.getCurrentUser();
        updateUI(currentUser);
        if (currentUser != null) {
            Log.println(Log.INFO, "FirebaseAuth sign in intent", "Already signed in.");
            signIn("test1@test.com", "12345678");
        } else {
            Log.println(Log.INFO, "FirebaseAuth sign in intent", "A new / returning user.");
            signUp("test1@test.com", "12345678");
        }

        // INITIALIZE RECEIVER
        IntentFilter filter = new IntentFilter(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        BroadcastReceiver mReceiver = new ScreenReceiver();
        registerReceiver(mReceiver, filter);

        // Initialize queue for network requests made by Volley.
        this.requestQueue = Volley.newRequestQueue(this);

        this.database = FirebaseDatabase.getInstance();
        this.morningRef = database.getReference("morning");
        initMorningTime();

         String name="empty";
        if (currentUser != null) {
            // Name, email address, and profile photo Url
            name = currentUser.getDisplayName();
            String email = currentUser.getEmail();
            Uri photoUrl = currentUser.getPhotoUrl();

            // Check if user's email is verified
            boolean emailVerified = currentUser.isEmailVerified();

            // The user's ID, unique to the Firebase project. Do NOT use this value to
            // authenticate with your backend server, if you have one. Use
            // FirebaseUser.getIdToken() instead.
            String uid = currentUser.getUid();
        }

        // Sign out
        AuthUI.getInstance()
                .signOut(this)
                .addOnCompleteListener(new OnCompleteListener<Void>() {
                    public void onComplete(@NonNull Task<Void> task) {
                        Log.println(Log.INFO ,"HomeActivity","Successfully signed out");
                    }
                });

            unregisterReceiver(mReceiver);
        }



    public static boolean isSameDay(Date date1, Date date2) {
        LocalDate localDate1 = date1.toInstant()
                .atZone(ZoneId.systemDefault())
                .toLocalDate();
        LocalDate localDate2 = date2.toInstant()
                .atZone(ZoneId.systemDefault())
                .toLocalDate();
        return localDate1.isEqual(localDate2);
    }

    private void initMorningTime() {
        ValueEventListener postListener = new ValueEventListener() {

            @Override
            public void onDataChange(DataSnapshot dataSnapshot) {
                Date currentTime = Calendar.getInstance().getTime();
                morning = dataSnapshot.getValue(Date.class);
                if(morning != null) {
                    if(!isSameDay(morning,currentTime)) {
                        Log.println(Log.INFO, "firebase", "Existing morning time changed onCreate: " + morning.toString());
                        morningRef.setValue(currentTime);
                    }
                }
                else
                {
                    morningRef.setValue(currentTime);
                    morning = dataSnapshot.getValue(Date.class);
                    Log.println(Log.INFO, "firebase", "New morning time registered onCreate: " + morning.toString());
                }
            }

            @Override
            public void onCancelled(DatabaseError databaseError) {
                // Getting Post failed, log a message
                Log.w("firebase", "Failed to read value.", databaseError.toException());
            }
        };
        morningRef.addListenerForSingleValueEvent(postListener);
    }

    private void signIn(String email, String password) {
        mAuth.signInWithEmailAndPassword(email, password)
                .addOnCompleteListener(this, new OnCompleteListener<AuthResult>() {
                    @Override
                    public void onComplete(@NonNull Task<AuthResult> task) {
                        if (task.isSuccessful()) {
                            // Sign in success, update UI with the signed-in user's information
                            Log.d("signIn", "signInWithEmail:success");
                            FirebaseUser user = mAuth.getCurrentUser();
                            updateUI(user);
                        } else {
                            // If sign in fails, display a message to the user.
                            Log.w("signIn", "signInWithEmail:failure", task.getException());
                            updateUI(null);
                        }

                        // ...
                    }
                });
    }

    private void signUp(String email, String password) {
        mAuth.createUserWithEmailAndPassword(email, password)
                .addOnCompleteListener(this, new OnCompleteListener<AuthResult>() {
                    @Override
                    public void onComplete(@NonNull Task<AuthResult> task) {
                        if (task.isSuccessful()) {
                            // Sign in success, update UI with the signed-in user's information
                            Log.d("signUp", "createUserWithEmail:success");
                            FirebaseUser user = mAuth.getCurrentUser();
                            updateUI(user);
                        } else {
                            // If sign in fails, display a message to the user.
                            Log.w("signUp", "createUserWithEmail:failure", task.getException());
                            updateUI(null);
                        }

                        // ...
                    }
                });
    }

    private void updateUI(FirebaseUser currentUser) {
    }


    @Override
    protected void onPause() {
        super.onPause();

        // WHEN THE SCREEN IS ABOUT TO TURN OFF
        if (ScreenReceiver.wasScreenOn) {
            // THIS IS THE CASE WHEN ONPAUSE() IS CALLED BY THE SYSTEM DUE TO A SCREEN STATE CHANGE
            System.out.println("SCREEN TURNED OFF");
        } else {
            // THIS IS WHEN ONPAUSE() IS CALLED WHEN THE SCREEN STATE HAS NOT CHANGED
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
            // THIS IS WHEN ONRESUME() IS CALLED DUE TO A SCREEN STATE CHANGE
            System.out.println("SCREEN TURNED ON");

            // Read from the database
            morningRef.addValueEventListener(new ValueEventListener() {

                // This method is called once every morning
                @Override
                public void onDataChange(DataSnapshot dataSnapshot) {
                    Date morning = dataSnapshot.getValue(Date.class);
                    Log.println(Log.INFO,"firebase",morning.toString());
                    TextView current_time_text_view = findViewById(R.id.morning_id);
                    current_time_text_view.setText(morning.toString());
                }

                @Override
                public void onCancelled(DatabaseError error) {
                    // Failed to read value
                    Log.w("firebase", "Failed to read value.", error.toException());
                }
            });
    }
}
